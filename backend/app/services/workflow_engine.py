from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.enums import (
    ApprovalAction,
    AssignmentStatus,
    ContractStatus,
    ContractType,
    WorkflowAction,
    WorkflowAssigneeMode,
    WorkflowInstanceStatus,
    WorkflowTargetType,
    WorkflowTaskStatus,
    WorkflowVersionStatus,
)
from app.models.approval import Approval
from app.models.approval_form import ApprovalForm, ApprovalFormAction
from app.models.contract import Contract
from app.models.organization import ExternalAssignment, Organization, Position, UserAssignment
from app.models.user import User
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowNode,
    WorkflowTask,
    WorkflowTaskAction,
    WorkflowVersion,
)
from app.schemas.workflow import WorkflowCandidate
from app.services.workflow_catalog import WORKFLOW_DEFINITIONS, WorkflowCatalogDefinition


@dataclass(frozen=True)
class WorkflowValidationIssue:
    code: str
    message: str
    user_id: int | None = None
    node_codes: tuple[str, ...] = ()


class WorkflowValidationError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class WorkflowActorSnapshot:
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str


def _workflow_actor_snapshot(
    actor: User,
    assignment: UserAssignment | None,
) -> WorkflowActorSnapshot:
    if actor.is_active and actor.is_superuser:
        return WorkflowActorSnapshot(
            organization_code="system.governance",
            organization_name="系统治理",
            position_code="system.superuser",
            position_name="超级管理员",
        )
    if assignment is None:
        raise WorkflowValidationError(
            "workflow_task_not_actionable",
            "The actor is not authorized for this task.",
        )
    return WorkflowActorSnapshot(
        organization_code=assignment.organization.code,
        organization_name=assignment.organization.name,
        position_code=assignment.position.code,
        position_name=assignment.position.name,
    )


class WorkflowTaskConflict(Exception):
    def __init__(
        self,
        *,
        actor_name: str,
        action: str,
        completed_at: datetime,
    ) -> None:
        super().__init__("task_already_completed")
        self.code = "task_already_completed"
        self.actor_name = actor_name
        self.action = action
        self.completed_at = completed_at


class _WorkflowTaskCASFailed(Exception):
    pass


WORKFLOW_CODE_BY_TARGET = {
    WorkflowTargetType.CONTRACT: "supply.contract.v2",
    WorkflowTargetType.PAYMENT_APPROVAL: "supply.payment.v2",
    WorkflowTargetType.BUSINESS_APPROVAL: "supply.business.v2",
}


def project_contract_action(
    db: Session,
    instance: WorkflowInstance,
    task: WorkflowTask,
    action: WorkflowTaskAction,
) -> None:
    legacy_action = {
        WorkflowAction.SUBMIT: ApprovalAction.APPROVE,
        WorkflowAction.APPROVE: ApprovalAction.APPROVE,
        WorkflowAction.RETURN: ApprovalAction.REJECT,
    }.get(action.action)
    if legacy_action is None:
        return
    common_values = {
        "approver_id": action.actor_id,
        "step": task.sequence,
        "approver_role": action.position_code[:32],
        "action": legacy_action,
        "comment": (
            "提交审批（业务经办）"
            if action.action == WorkflowAction.SUBMIT and not action.comment
            else action.comment
        ),
        "signature_snapshot": action.signature_snapshot,
        "workflow_task_action_id": action.id,
        "organization_code": action.organization_code,
        "organization_name": action.organization_name,
        "position_code": action.position_code,
        "position_name": action.position_name,
    }
    if instance.target_type == WorkflowTargetType.CONTRACT:
        if db.scalar(select(exists().where(Approval.workflow_task_action_id == action.id))):
            return
        db.add(Approval(contract_id=instance.target_id, **common_values))
    elif instance.target_type in {
        WorkflowTargetType.PAYMENT_APPROVAL,
        WorkflowTargetType.BUSINESS_APPROVAL,
    }:
        if db.scalar(select(exists().where(
            ApprovalFormAction.workflow_task_action_id == action.id
        ))):
            return
        db.add(ApprovalFormAction(form_id=instance.target_id, **common_values))


def ensure_workflow_version_mutable(version: WorkflowVersion) -> None:
    if version.status != WorkflowVersionStatus.DRAFT:
        raise WorkflowValidationError(
            "workflow_version_immutable",
            "Published or retired workflow versions cannot be changed.",
            {"version_id": version.id},
        )


def _periods_overlap(left: UserAssignment, right: UserAssignment) -> bool:
    left_end = left.valid_until or date.max
    right_end = right.valid_until or date.max
    return left.valid_from <= right_end and right.valid_from <= left_end


def validate_workflow_version(
    db: Session,
    version: WorkflowVersion,
) -> list[WorkflowValidationIssue]:
    nodes_by_position: dict[str, list[WorkflowNode]] = {}
    for workflow_node in version.nodes:
        nodes_by_position.setdefault(workflow_node.position_code, []).append(workflow_node)

    assignments = list(db.scalars(
        select(UserAssignment)
        .join(UserAssignment.user)
        .join(UserAssignment.organization)
        .join(UserAssignment.position)
        .where(
            UserAssignment.status == AssignmentStatus.ACTIVE,
            User.is_active.is_(True),
            Organization.is_active.is_(True),
            Position.is_active.is_(True),
            Position.code.in_(nodes_by_position),
        )
        .options(
            joinedload(UserAssignment.user),
            joinedload(UserAssignment.position),
        )
        .order_by(UserAssignment.user_id, UserAssignment.valid_from, UserAssignment.id)
    ))

    assignments_by_user: dict[int, list[UserAssignment]] = {}
    for assignment in assignments:
        assignments_by_user.setdefault(assignment.user_id, []).append(assignment)

    issues: list[WorkflowValidationIssue] = []
    for user_id, user_assignments in assignments_by_user.items():
        conflicting_codes: set[str] = set()
        for index, left in enumerate(user_assignments):
            for right in user_assignments[index + 1:]:
                if left.position_id == right.position_id or not _periods_overlap(left, right):
                    continue
                for workflow_node in nodes_by_position[left.position.code]:
                    conflicting_codes.add(workflow_node.code)
                for workflow_node in nodes_by_position[right.position.code]:
                    conflicting_codes.add(workflow_node.code)
        if conflicting_codes:
            node_codes = tuple(
                workflow_node.code
                for workflow_node in sorted(version.nodes, key=lambda item: item.sequence)
                if workflow_node.code in conflicting_codes
            )
            issues.append(WorkflowValidationIssue(
                code="workflow_assignment_conflict",
                message="Active assignments allow one user to satisfy different workflow nodes over an overlapping period.",
                user_id=user_id,
                node_codes=node_codes,
            ))
    return issues


def _active_assignments(
    db: Session,
    position_codes: set[str],
    on_date: date,
    user_ids: set[int] | None = None,
) -> list[UserAssignment]:
    statement = (
        select(UserAssignment)
        .join(UserAssignment.user)
        .join(UserAssignment.organization)
        .join(UserAssignment.position)
        .where(
            UserAssignment.status == AssignmentStatus.ACTIVE,
            UserAssignment.valid_from <= on_date,
            (UserAssignment.valid_until.is_(None) | (UserAssignment.valid_until >= on_date)),
            User.is_active.is_(True),
            Organization.is_active.is_(True),
            Position.is_active.is_(True),
            Position.code.in_(position_codes),
        )
        .options(
            joinedload(UserAssignment.user),
            joinedload(UserAssignment.organization),
            joinedload(UserAssignment.position),
            joinedload(UserAssignment.external_detail),
        )
        .order_by(User.full_name, User.id, UserAssignment.id)
    )
    if user_ids is not None:
        statement = statement.where(UserAssignment.user_id.in_(user_ids))
    return list(db.scalars(statement))


def _assignment_has_required_scope(assignment: UserAssignment) -> bool:
    if assignment.position.code != "external.legal_counsel":
        return True
    detail: ExternalAssignment | None = assignment.external_detail
    return detail is not None and "contract_legal_review" in detail.service_scopes


def _published_workflow(db: Session, workflow_code: str) -> tuple[WorkflowDefinition, WorkflowVersion]:
    definition = db.scalar(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.code == workflow_code)
        .options(joinedload(WorkflowDefinition.active_version).joinedload(WorkflowVersion.nodes))
    )
    version = definition.active_version if definition is not None else None
    if version is None or version.status != WorkflowVersionStatus.PUBLISHED:
        raise WorkflowValidationError(
            "workflow_not_published",
            "The requested workflow has no active published version.",
            {"workflow_code": workflow_code},
        )
    return definition, version


def eligible_designated_users(
    db: Session,
    workflow_code: str,
    node_code: str,
    on_date: date,
    exclude_user_id: int | None = None,
) -> list[WorkflowCandidate]:
    _, version = _published_workflow(db, workflow_code)
    node = next((item for item in version.nodes if item.code == node_code), None)
    if node is None:
        raise WorkflowValidationError(
            "unknown_workflow_node",
            "The requested node is not part of the active workflow.",
            {"workflow_code": workflow_code, "node_code": node_code},
        )
    if node.assignee_mode != WorkflowAssigneeMode.DESIGNATED_USER:
        raise WorkflowValidationError(
            "workflow_node_not_designated",
            "Candidates can only be requested for designated-user nodes.",
            {"workflow_code": workflow_code, "node_code": node_code},
        )

    return eligible_users_for_position(db, node.position_code, on_date, exclude_user_id)


def eligible_users_for_position(
    db: Session,
    position_code: str,
    on_date: date,
    exclude_user_id: int | None = None,
) -> list[WorkflowCandidate]:
    candidates: list[WorkflowCandidate] = []
    seen_users: set[int] = set()
    for assignment in _active_assignments(db, {position_code}, on_date):
        if (
            assignment.user_id == exclude_user_id
            or assignment.user_id in seen_users
            or not _assignment_has_required_scope(assignment)
        ):
            continue
        seen_users.add(assignment.user_id)
        candidates.append(WorkflowCandidate(
            user_id=assignment.user_id,
            full_name=assignment.user.full_name,
            assignment_id=assignment.id,
            organization_code=assignment.organization.code,
            organization_name=assignment.organization.name,
            position_code=assignment.position.code,
            position_name=assignment.position.name,
            valid_from=assignment.valid_from,
            valid_until=assignment.valid_until,
        ))
    return candidates


def _catalog_nodes(definition: WorkflowCatalogDefinition) -> tuple[tuple, ...]:
    return tuple(
        (
            sequence,
            item.code,
            item.name,
            item.position_code,
            item.mode,
            item.auto_complete_on_submit,
            item.allow_reject,
        )
        for sequence, item in enumerate(definition.nodes)
    )


def _persisted_nodes(version: WorkflowVersion) -> tuple[tuple, ...]:
    return tuple(
        (
            item.sequence,
            item.code,
            item.name,
            item.position_code,
            item.assignee_mode.value,
            item.auto_complete_on_submit,
            item.allow_reject,
        )
        for item in sorted(version.nodes, key=lambda workflow_node: workflow_node.sequence)
    )


def _load_definition(db: Session, code: str) -> WorkflowDefinition | None:
    return db.scalar(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.code == code)
        .options(joinedload(WorkflowDefinition.versions).joinedload(WorkflowVersion.nodes))
    )


def _raise_catalog_drift(workflow_code: str, version: int | None = None) -> None:
    details = {"workflow_code": workflow_code}
    if version is not None:
        details["version"] = version
    raise WorkflowValidationError(
        "workflow_catalog_drift",
        "Persisted workflow content differs from the confirmed catalog.",
        details,
    )


def _verify_published_catalog(db: Session) -> None:
    with db.no_autoflush:
        for catalog_definition in WORKFLOW_DEFINITIONS:
            definition = _load_definition(db, catalog_definition.code)
            if (
                definition is None
                or definition.name != catalog_definition.name
                or definition.target_type != catalog_definition.target_type
            ):
                _raise_catalog_drift(catalog_definition.code)
            version = next(
                (item for item in definition.versions if item.version == catalog_definition.version),
                None,
            )
            if (
                version is None
                or version.status != WorkflowVersionStatus.PUBLISHED
                or _persisted_nodes(version) != _catalog_nodes(catalog_definition)
                or definition.active_version_id != version.id
            ):
                _raise_catalog_drift(catalog_definition.code, catalog_definition.version)


def _is_catalog_unique_race(error: IntegrityError) -> bool:
    message = " ".join(
        str(part).lower()
        for part in (error.statement, error.orig)
        if part is not None
    )
    is_unique = any(token in message for token in ("unique", "duplicate"))
    is_catalog_constraint = any(token in message for token in (
        "wf_definition.code",
        "ix_wf_definition_code",
        "uq_workflow_version_definition_version",
        "wf_version.definition_id, wf_version.version",
    ))
    return is_unique and is_catalog_constraint


def _seed_workflow_definitions(db: Session, publisher_id: int) -> None:
    pending_publications: list[tuple[WorkflowDefinition, WorkflowVersion]] = []
    for catalog_definition in WORKFLOW_DEFINITIONS:
        with db.no_autoflush:
            definition = _load_definition(db, catalog_definition.code)
        if definition is None:
            definition = WorkflowDefinition(
                code=catalog_definition.code,
                name=catalog_definition.name,
                target_type=catalog_definition.target_type,
            )
            db.add(definition)
            db.flush()
        elif (
            definition.name != catalog_definition.name
            or definition.target_type != catalog_definition.target_type
        ):
            _raise_catalog_drift(catalog_definition.code)

        version = next(
            (item for item in definition.versions if item.version == catalog_definition.version),
            None,
        )
        if version is not None:
            if (
                version.status != WorkflowVersionStatus.PUBLISHED
                or _persisted_nodes(version) != _catalog_nodes(catalog_definition)
                or definition.active_version_id != version.id
            ):
                _raise_catalog_drift(catalog_definition.code, catalog_definition.version)
            continue

        version = WorkflowVersion(
            definition_id=definition.id,
            version=catalog_definition.version,
            status=WorkflowVersionStatus.DRAFT,
        )
        db.add(version)
        db.flush()
        version.nodes = [
            WorkflowNode(
                sequence=sequence,
                code=item.code,
                name=item.name,
                position_code=item.position_code,
                assignee_mode=WorkflowAssigneeMode(item.mode),
                auto_complete_on_submit=item.auto_complete_on_submit,
                allow_reject=item.allow_reject,
            )
            for sequence, item in enumerate(catalog_definition.nodes)
        ]
        db.flush()
        pending_publications.append((definition, version))

    issues = [
        issue
        for _, version in pending_publications
        for issue in validate_workflow_version(db, version)
    ]
    if issues:
        raise WorkflowValidationError(
            "workflow_validation_failed",
            "Workflow publication is blocked by assignment conflicts.",
            {"issues": [issue.__dict__ for issue in issues]},
        )

    published_at = datetime.now()
    for definition, version in pending_publications:
        version.status = WorkflowVersionStatus.PUBLISHED
        version.published_at = published_at
        version.published_by = publisher_id
        definition.active_version_id = version.id
    db.flush()


def seed_workflow_definitions(db: Session, publisher_id: int) -> None:
    connection = db.connection()
    _ensure_sqlite_outer_transaction(connection)
    catalog_session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        _seed_workflow_definitions(catalog_session, publisher_id)
        catalog_session.commit()
    except IntegrityError as error:
        catalog_session.rollback()
        if not _is_catalog_unique_race(error):
            raise
        _expire_parent_catalog_state(db)
        _verify_published_catalog(db)
    except Exception:
        catalog_session.rollback()
        raise
    finally:
        catalog_session.close()
    _expire_parent_catalog_state(db)


def _ensure_sqlite_outer_transaction(connection, *, immediate: bool = False) -> None:
    if connection.dialect.name != "sqlite":
        return
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")


def _expire_parent_catalog_state(db: Session) -> None:
    catalog_types = (WorkflowDefinition, WorkflowVersion, WorkflowNode)
    with db.no_autoflush:
        for instance in list(db.identity_map.values()):
            if isinstance(instance, catalog_types):
                db.expire(instance)


def _workflow_target(
    db: Session,
    target_type: WorkflowTargetType,
    target_id: int,
):
    if target_type == WorkflowTargetType.CONTRACT:
        target = db.scalar(
            select(Contract).where(Contract.id == target_id).with_for_update()
        )
    else:
        target = db.scalar(
            select(ApprovalForm).where(ApprovalForm.id == target_id).with_for_update()
        )
        expected_form_type = (
            ContractType.PAYMENT
            if target_type == WorkflowTargetType.PAYMENT_APPROVAL
            else ContractType.BUSINESS
        )
        if target is not None and target.form_type != expected_form_type:
            target = None
    if target is None:
        raise WorkflowValidationError(
            "workflow_target_not_found",
            "The requested workflow target does not exist.",
            {"target_type": target_type.value, "target_id": target_id},
        )
    return target


def _validate_start_assignments(
    db: Session,
    version: WorkflowVersion,
    submitter: User,
    designated_users: dict[str, int],
    submitted_on: date,
) -> tuple[UserAssignment | None, dict[str, UserAssignment]]:
    submitter_id = submitter.id
    designated_nodes = {
        item.code: item
        for item in version.nodes
        if item.assignee_mode == WorkflowAssigneeMode.DESIGNATED_USER
    }
    missing_codes = sorted(set(designated_nodes) - set(designated_users))
    if missing_codes:
        raise WorkflowValidationError(
            "missing_designated_user",
            "Every designated workflow node requires one selected user.",
            {"node_codes": missing_codes},
        )
    unknown_codes = sorted(set(designated_users) - set(designated_nodes))
    if unknown_codes:
        raise WorkflowValidationError(
            "unknown_designated_node",
            "Selected users include nodes that are not designated in this workflow.",
            {"node_codes": unknown_codes},
        )

    selected_user_ids = list(designated_users.values())
    if len(set(selected_user_ids)) != len(selected_user_ids) or submitter_id in selected_user_ids:
        raise WorkflowValidationError(
            "duplicate_workflow_actor",
            "One person cannot occupy two nodes in the same workflow.",
        )

    workflow_position_codes = {item.position_code for item in version.nodes}
    assignments = _active_assignments(
        db,
        workflow_position_codes,
        submitted_on,
        {submitter_id, *selected_user_ids},
    )
    assignments_by_user: dict[int, list[UserAssignment]] = {}
    for assignment in assignments:
        if _assignment_has_required_scope(assignment):
            assignments_by_user.setdefault(assignment.user_id, []).append(assignment)

    submit_node = next(
        item for item in version.nodes if item.sequence == 0 and item.auto_complete_on_submit
    )
    submitter_assignments = assignments_by_user.get(submitter_id, [])
    submit_assignment = next(
        (item for item in submitter_assignments if item.position.code == submit_node.position_code),
        None,
    )
    if submit_assignment is None and not (
        submitter.is_active and submitter.is_superuser
    ):
        raise WorkflowValidationError(
            "ineligible_workflow_submitter",
            "The submitter is not eligible for the submit node.",
            {"node_code": submit_node.code, "user_id": submitter_id},
        )
    if any(item.position.code != submit_node.position_code for item in submitter_assignments):
        raise WorkflowValidationError(
            "duplicate_workflow_actor",
            "One person cannot occupy two nodes in the same workflow.",
            {"user_id": submitter_id},
        )

    selected_assignments: dict[str, UserAssignment] = {}
    for node_code, user_id in designated_users.items():
        node = designated_nodes[node_code]
        user_assignments = assignments_by_user.get(user_id, [])
        assignment = next(
            (item for item in user_assignments if item.position.code == node.position_code),
            None,
        )
        if assignment is None:
            raise WorkflowValidationError(
                "ineligible_designated_user",
                "The selected user is not eligible for the designated node.",
                {"node_code": node_code, "user_id": user_id},
            )
        if any(item.position.code != node.position_code for item in user_assignments):
            raise WorkflowValidationError(
                "duplicate_workflow_actor",
                "One person cannot occupy two nodes in the same workflow.",
                {"user_id": user_id},
            )
        selected_assignments[node_code] = assignment
    return submit_assignment, selected_assignments


def _start_workflow(
    db: Session,
    target_type: WorkflowTargetType,
    target_id: int,
    submitter_id: int,
    designated_users: dict[str, int],
    submitted_at: datetime,
) -> int:
    submitter = db.get(User, submitter_id)
    if submitter is None:
        raise WorkflowValidationError(
            "ineligible_workflow_submitter",
            "The submitter is not eligible for the submit node.",
            {"user_id": submitter_id},
        )
    target = _workflow_target(db, target_type, target_id)
    if target.created_by != submitter_id:
        raise WorkflowValidationError(
            "workflow_submitter_not_owner",
            "Only the target creator can start its workflow.",
            {"target_type": target_type.value, "target_id": target_id},
        )
    if target.status != ContractStatus.DRAFT or target.workflow_instance_id is not None:
        raise WorkflowValidationError(
            "workflow_already_started",
            "The target already has a workflow instance.",
            {"target_type": target_type.value, "target_id": target_id},
        )
    existing_instance = db.scalar(
        select(WorkflowInstance.id).where(
            WorkflowInstance.target_type == target_type,
            WorkflowInstance.target_id == target_id,
        )
    )
    if existing_instance is not None:
        raise WorkflowValidationError(
            "workflow_already_started",
            "The target already has a workflow instance.",
            {"target_type": target_type.value, "target_id": target_id},
        )

    workflow_code = WORKFLOW_CODE_BY_TARGET[target_type]
    definition, version = _published_workflow(db, workflow_code)
    submit_assignment, selected_assignments = _validate_start_assignments(
        db,
        version,
        submitter,
        designated_users,
        submitted_at.date(),
    )
    actor_snapshot = _workflow_actor_snapshot(submitter, submit_assignment)
    nodes = sorted(version.nodes, key=lambda item: item.sequence)
    next_node = next((item for item in nodes if not item.auto_complete_on_submit), None)
    if next_node is None:
        raise WorkflowValidationError(
            "workflow_has_no_approval_node",
            "The workflow contains no approval node after submission.",
        )

    instance = WorkflowInstance(
        definition_id=definition.id,
        version_id=version.id,
        target_type=target_type,
        target_id=target_id,
        status=WorkflowInstanceStatus.ACTIVE,
        current_sequence=next_node.sequence,
        submitted_by=submitter_id,
        submitted_at=submitted_at,
    )
    db.add(instance)
    db.flush()

    tasks: list[WorkflowTask] = []
    position_names = dict(db.execute(select(Position.code, Position.name).where(
        Position.code.in_({node.position_code for node in nodes})
    )).all())
    for node in nodes:
        selected_assignment = selected_assignments.get(node.code)
        if node.auto_complete_on_submit:
            task_status = WorkflowTaskStatus.APPROVED
        elif node.sequence == next_node.sequence:
            task_status = WorkflowTaskStatus.ACTIVE
        else:
            task_status = WorkflowTaskStatus.PENDING
        task = WorkflowTask(
            instance_id=instance.id,
            node_id=node.id,
            sequence=node.sequence,
            status=task_status,
            required_position_code=node.position_code,
            required_position_name=position_names.get(node.position_code, node.position_code),
            assignee_mode=node.assignee_mode,
            designated_user_id=(selected_assignment.user_id if selected_assignment else None),
            designated_assignment_id=(selected_assignment.id if selected_assignment else None),
            activated_at=(submitted_at if task_status == WorkflowTaskStatus.ACTIVE else None),
            completed_at=(submitted_at if task_status == WorkflowTaskStatus.APPROVED else None),
        )
        db.add(task)
        tasks.append(task)
    db.flush()

    submit_task = next(item for item in tasks if item.sequence == 0)
    submit_action = WorkflowTaskAction(
        task_id=submit_task.id,
        action=WorkflowAction.SUBMIT,
        actor_id=submitter_id,
        actor_name=submitter.full_name,
        organization_code=actor_snapshot.organization_code,
        organization_name=actor_snapshot.organization_name,
        position_code=actor_snapshot.position_code,
        position_name=actor_snapshot.position_name,
        signature_snapshot=submitter.signature,
    )
    db.add(submit_action)
    db.flush()
    project_contract_action(db, instance, submit_task, submit_action)
    target.status = ContractStatus.PENDING
    target.current_step = next_node.sequence
    target.workflow_instance_id = instance.id
    db.flush()
    return instance.id


def _is_duplicate_workflow_target(error: IntegrityError) -> bool:
    message = " ".join(
        str(part).lower()
        for part in (error.statement, error.orig)
        if part is not None
    )
    return any(token in message for token in ("unique", "duplicate")) and any(
        token in message
        for token in (
            "uq_workflow_instance_target",
            "wf_instance.target_type, wf_instance.target_id",
        )
    )


def start_workflow(
    db: Session,
    target_type: WorkflowTargetType,
    target_id: int,
    submitter: User,
    designated_users: dict[str, int],
) -> WorkflowInstance:
    target_type = WorkflowTargetType(target_type)
    with db.no_autoflush:
        submitter_id = submitter.id
        connection = db.connection()
    _ensure_sqlite_outer_transaction(connection)
    workflow_session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    instance_id = None
    try:
        instance_id = _start_workflow(
            workflow_session,
            target_type,
            target_id,
            submitter_id,
            dict(designated_users),
            datetime.now(),
        )
        workflow_session.commit()
    except IntegrityError as error:
        workflow_session.rollback()
        if not _is_duplicate_workflow_target(error):
            raise
        raise WorkflowValidationError(
            "workflow_already_started",
            "The target already has a workflow instance.",
            {"target_type": target_type.value, "target_id": target_id},
        ) from error
    except Exception:
        workflow_session.rollback()
        raise
    finally:
        workflow_session.close()

    _expire_parent_workflow_state(db, target_type, target_id)
    with db.no_autoflush:
        return db.get(WorkflowInstance, instance_id)


def _materialize_legacy_workflow(
    db: Session,
    target_type: WorkflowTargetType,
    target_id: int,
    current_sequence: int,
    designated_assignment_ids: dict[str, int],
    materialized_at: datetime,
    on_date: date,
) -> int:
    target = _workflow_target(db, target_type, target_id)
    if target.status != ContractStatus.PENDING or target.workflow_instance_id is not None:
        raise WorkflowValidationError(
            "legacy_workflow_not_migratable",
            "Only pending legacy targets without a workflow instance can be migrated.",
            {"target_type": target_type.value, "target_id": target_id},
        )
    if target.current_step != current_sequence:
        raise WorkflowValidationError(
            "legacy_workflow_stale_current_step",
            "The legacy target current step changed after migration classification.",
            {
                "target_type": target_type.value,
                "target_id": target_id,
                "scanned_current_step": current_sequence,
                "locked_current_step": target.current_step,
            },
        )
    if db.scalar(select(WorkflowInstance.id).where(
        WorkflowInstance.target_type == target_type,
        WorkflowInstance.target_id == target_id,
    )) is not None:
        raise WorkflowValidationError(
            "workflow_already_started",
            "The target already has a workflow instance.",
            {"target_type": target_type.value, "target_id": target_id},
        )

    workflow_code = WORKFLOW_CODE_BY_TARGET[target_type]
    definition, version = _published_workflow(db, workflow_code)
    catalog_definition = next(
        item for item in WORKFLOW_DEFINITIONS if item.code == workflow_code
    )
    if (
        definition.name != catalog_definition.name
        or definition.target_type != catalog_definition.target_type
        or version.version != catalog_definition.version
        or _persisted_nodes(version) != _catalog_nodes(catalog_definition)
    ):
        _raise_catalog_drift(workflow_code, catalog_definition.version)
    nodes = sorted(version.nodes, key=lambda item: item.sequence)
    current_node = next(
        (item for item in nodes if item.sequence == current_sequence), None
    )
    if (
        current_node is None
        or current_node.assignee_mode != WorkflowAssigneeMode.SHARED_POSITION
    ):
        raise WorkflowValidationError(
            "legacy_workflow_current_step_not_shared",
            "Legacy migration requires a current shared-position node.",
            {"current_sequence": current_sequence},
        )

    future_designated_nodes = {
        item.code: item
        for item in nodes
        if item.sequence > current_sequence
        and item.assignee_mode == WorkflowAssigneeMode.DESIGNATED_USER
    }
    if set(designated_assignment_ids) != set(future_designated_nodes):
        raise WorkflowValidationError(
            "legacy_workflow_designations_incomplete",
            "Every future designated node requires one validated assignment.",
            {"node_codes": sorted(future_designated_nodes)},
        )
    selected_assignments: dict[str, UserAssignment] = {}
    selected_user_ids: set[int] = set()
    for node_code, assignment_id in designated_assignment_ids.items():
        node = future_designated_nodes[node_code]
        eligible_assignments = [
            item for item in _active_assignments(
                db, {node.position_code}, on_date
            )
            if _assignment_has_required_scope(item)
        ]
        eligible_user_ids = {item.user_id for item in eligible_assignments}
        assignment = next(
            (item for item in eligible_assignments if item.id == assignment_id), None
        )
        if (
            len(eligible_user_ids) != 1
            or assignment is None
            or assignment.position.code != node.position_code
            or assignment.user_id == target.created_by
            or assignment.user_id in selected_user_ids
        ):
            raise WorkflowValidationError(
                "legacy_workflow_designation_invalid",
                "A future designated assignment is no longer uniquely eligible.",
                {"node_code": node_code, "assignment_id": assignment_id},
            )
        selected_assignments[node_code] = assignment
        selected_user_ids.add(assignment.user_id)

    instance = WorkflowInstance(
        definition_id=definition.id,
        version_id=version.id,
        target_type=target_type,
        target_id=target_id,
        status=WorkflowInstanceStatus.ACTIVE,
        current_sequence=current_sequence,
        submitted_by=target.created_by,
        submitted_at=materialized_at,
    )
    db.add(instance)
    db.flush()
    position_names = dict(db.execute(select(Position.code, Position.name).where(
        Position.code.in_({node.position_code for node in nodes})
    )).all())
    for node in nodes:
        selected_assignment = selected_assignments.get(node.code)
        if node.sequence < current_sequence:
            task_status = WorkflowTaskStatus.APPROVED
        elif node.sequence == current_sequence:
            task_status = WorkflowTaskStatus.ACTIVE
        else:
            task_status = WorkflowTaskStatus.PENDING
        db.add(WorkflowTask(
            instance_id=instance.id,
            node_id=node.id,
            sequence=node.sequence,
            status=task_status,
            required_position_code=node.position_code,
            required_position_name=position_names.get(node.position_code, node.position_code),
            assignee_mode=node.assignee_mode,
            designated_user_id=(selected_assignment.user_id if selected_assignment else None),
            designated_assignment_id=(selected_assignment.id if selected_assignment else None),
            activated_at=(materialized_at if task_status == WorkflowTaskStatus.ACTIVE else None),
        ))
    target.workflow_instance_id = instance.id
    db.flush()
    return instance.id


def materialize_legacy_workflow(
    db: Session,
    target_type: WorkflowTargetType,
    target_id: int,
    current_sequence: int,
    designated_assignment_ids: dict[str, int],
    materialized_at: datetime,
    on_date: date,
) -> WorkflowInstance:
    target_type = WorkflowTargetType(target_type)
    with db.no_autoflush:
        connection = db.connection()
    _ensure_sqlite_outer_transaction(connection)
    workflow_session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        instance_id = _materialize_legacy_workflow(
            workflow_session,
            target_type,
            target_id,
            current_sequence,
            dict(designated_assignment_ids),
            materialized_at,
            on_date,
        )
        workflow_session.commit()
    except IntegrityError as error:
        workflow_session.rollback()
        if not _is_duplicate_workflow_target(error):
            raise
        raise WorkflowValidationError(
            "workflow_already_started",
            "The target already has a workflow instance.",
            {"target_type": target_type.value, "target_id": target_id},
        ) from error
    except Exception:
        workflow_session.rollback()
        raise
    finally:
        workflow_session.close()

    _expire_parent_workflow_state(db, target_type, target_id)
    with db.no_autoflush:
        return db.get(WorkflowInstance, instance_id)


def _expire_parent_workflow_state(
    db: Session,
    target_type: WorkflowTargetType,
    target_id: int,
) -> None:
    target_type_class = Contract if target_type == WorkflowTargetType.CONTRACT else ApprovalForm
    workflow_types = (WorkflowInstance, WorkflowTask, WorkflowTaskAction)
    with db.no_autoflush:
        for instance in list(db.identity_map.values()):
            if isinstance(instance, workflow_types):
                db.expire(instance)
            elif isinstance(instance, target_type_class) and instance.id == target_id:
                db.expire(instance)


def _task_assignment_is_effective(
    task: WorkflowTask,
    assignment: UserAssignment | None,
    user: User,
    on_date: date,
) -> bool:
    return (
        assignment is not None
        and assignment.user_id == user.id
        and assignment.is_effective_on(on_date)
        and assignment.position.code == task.required_position_code
        and user.is_active
        and assignment.organization.is_active
        and assignment.position.is_active
        and _assignment_has_required_scope(assignment)
    )


def _designated_task_assignment_is_effective(
    task: WorkflowTask,
    assignment: UserAssignment | None,
    on_date: date,
) -> bool:
    return (
        assignment is not None
        and assignment.user_id == task.designated_user_id
        and assignment.is_effective_on(on_date)
        and assignment.user.is_active
        and assignment.position.code == task.required_position_code
        and assignment.organization.is_active
        and assignment.position.is_active
        and _assignment_has_required_scope(assignment)
    )


def _designated_task_assignment(
    db: Session,
    task: WorkflowTask,
) -> UserAssignment | None:
    return db.scalar(
        select(UserAssignment)
        .where(UserAssignment.id == task.designated_assignment_id)
        .options(
            joinedload(UserAssignment.user),
            joinedload(UserAssignment.organization),
            joinedload(UserAssignment.position),
            joinedload(UserAssignment.external_detail),
        )
    )


def _mark_invalid_designated_task(
    db: Session,
    task: WorkflowTask,
    on_date: date,
) -> UserAssignment | None:
    assignment = _designated_task_assignment(db, task)
    if _designated_task_assignment_is_effective(task, assignment, on_date):
        return assignment
    db.execute(
        update(WorkflowTask)
        .where(
            WorkflowTask.id == task.id,
            WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
        )
        .values(status=WorkflowTaskStatus.AWAITING_REASSIGNMENT)
    )
    db.expire(task)
    return None


def _actor_has_other_workflow_role(
    db: Session,
    task: WorkflowTask,
    user_id: int,
) -> bool:
    other_task = WorkflowTask.__table__.alias("other_workflow_task")
    other_action = WorkflowTaskAction.__table__.alias("other_workflow_action")
    return db.scalar(
        select(exists().where(
            other_task.c.instance_id == task.instance_id,
            other_task.c.id != task.id,
            or_(
                other_task.c.designated_user_id == user_id,
                exists().where(
                    other_action.c.task_id == other_task.c.id,
                    other_action.c.actor_id == user_id,
                ),
            ),
        ))
    )


def _effective_task_assignment(
    db: Session,
    task: WorkflowTask,
    user: User,
    on_date: date,
) -> UserAssignment | None:
    if task.status != WorkflowTaskStatus.ACTIVE:
        return None
    if task.assignee_mode == WorkflowAssigneeMode.DESIGNATED_USER:
        assignment = _mark_invalid_designated_task(db, task, on_date)
        if (
            assignment is None
            or not user.is_active
            or user.id != task.designated_user_id
            or _actor_has_other_workflow_role(db, task, user.id)
        ):
            return None
        return assignment if _task_assignment_is_effective(task, assignment, user, on_date) else None

    if not user.is_active or _actor_has_other_workflow_role(db, task, user.id):
        return None
    if task.instance.submitted_by == user.id:
        return None
    assignments = _active_assignments(
        db,
        {task.required_position_code},
        on_date,
        {user.id},
    )
    return next(
        (item for item in assignments if _assignment_has_required_scope(item)),
        None,
    )


def task_is_actionable_by(
    db: Session,
    task: WorkflowTask,
    user: User,
    on_date: date | None = None,
) -> bool:
    if user.is_superuser:
        return user.is_active and task.status == WorkflowTaskStatus.ACTIVE
    return _effective_task_assignment(db, task, user, on_date or date.today()) is not None


def refresh_invalid_designated_tasks(
    db: Session,
    on_date: date | None = None,
) -> None:
    effective_date = on_date or date.today()
    tasks = list(db.scalars(
        select(WorkflowTask)
        .where(
            WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
            WorkflowTask.assignee_mode == WorkflowAssigneeMode.DESIGNATED_USER,
        )
        .options(
            joinedload(WorkflowTask.designated_user),
            joinedload(WorkflowTask.designated_assignment).joinedload(UserAssignment.organization),
            joinedload(WorkflowTask.designated_assignment).joinedload(UserAssignment.position),
            joinedload(WorkflowTask.designated_assignment).joinedload(UserAssignment.external_detail),
        )
    ))
    for task in tasks:
        if not _designated_task_assignment_is_effective(
            task, task.designated_assignment, effective_date
        ):
            db.execute(
                update(WorkflowTask)
                .where(
                    WorkflowTask.id == task.id,
                    WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
                )
                .values(status=WorkflowTaskStatus.AWAITING_REASSIGNMENT)
            )
    db.flush()


def my_active_tasks(
    db: Session,
    user: User,
    target_type: WorkflowTargetType | None = None,
) -> list[WorkflowTask]:
    if not user.is_active:
        return []
    if user.is_superuser:
        statement = (
            select(WorkflowTask)
            .join(WorkflowTask.instance)
            .where(WorkflowTask.status == WorkflowTaskStatus.ACTIVE)
            .options(joinedload(WorkflowTask.instance), joinedload(WorkflowTask.node))
            .order_by(WorkflowInstance.submitted_at, WorkflowTask.sequence, WorkflowTask.id)
        )
        if target_type is not None:
            statement = statement.where(
                WorkflowInstance.target_type == WorkflowTargetType(target_type)
            )
        return list(db.scalars(statement))
    effective_date = date.today()
    assignment_exists = exists(
        select(UserAssignment.id)
        .join(UserAssignment.organization)
        .join(UserAssignment.position)
        .where(
            UserAssignment.user_id == user.id,
            UserAssignment.status == AssignmentStatus.ACTIVE,
            UserAssignment.valid_from <= effective_date,
            (UserAssignment.valid_until.is_(None) | (UserAssignment.valid_until >= effective_date)),
            Organization.is_active.is_(True),
            Position.is_active.is_(True),
            Position.code == WorkflowTask.required_position_code,
        )
    )
    statement = (
        select(WorkflowTask)
        .join(WorkflowTask.instance)
        .where(
            WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
            or_(
                WorkflowTask.designated_user_id == user.id,
                (
                    WorkflowTask.assignee_mode == WorkflowAssigneeMode.SHARED_POSITION
                )
                & assignment_exists
                & (WorkflowInstance.submitted_by != user.id),
            ),
        )
        .options(joinedload(WorkflowTask.instance), joinedload(WorkflowTask.node))
        .order_by(WorkflowInstance.submitted_at, WorkflowTask.sequence, WorkflowTask.id)
    )
    if target_type is not None:
        statement = statement.where(WorkflowInstance.target_type == WorkflowTargetType(target_type))
    tasks = list(db.scalars(statement))
    return [
        task for task in tasks
        if task_is_actionable_by(db, task, user, effective_date)
    ]


def actionable_active_task_counts(
    db: Session,
    user: User,
) -> dict[WorkflowTargetType, int]:
    if not user.is_active:
        return {}
    effective_date = date.today()
    refresh_invalid_designated_tasks(db, effective_date)
    if user.is_superuser:
        rows = db.execute(
            select(WorkflowInstance.target_type, func.count(WorkflowTask.id))
            .join(WorkflowTask, WorkflowTask.instance_id == WorkflowInstance.id)
            .where(WorkflowTask.status == WorkflowTaskStatus.ACTIVE)
            .group_by(WorkflowInstance.target_type)
        ).all()
        return {
            WorkflowTargetType(target_type): count
            for target_type, count in rows
        }
    effective_assignment = exists(
        select(UserAssignment.id)
        .join(UserAssignment.organization)
        .join(UserAssignment.position)
        .where(
            UserAssignment.user_id == user.id,
            UserAssignment.status == AssignmentStatus.ACTIVE,
            UserAssignment.valid_from <= effective_date,
            (UserAssignment.valid_until.is_(None) | (UserAssignment.valid_until >= effective_date)),
            Organization.is_active.is_(True),
            Position.is_active.is_(True),
            Position.code == WorkflowTask.required_position_code,
        )
    )
    designated_assignment = exists(
        select(UserAssignment.id)
        .join(UserAssignment.organization)
        .join(UserAssignment.position)
        .where(
            UserAssignment.id == WorkflowTask.designated_assignment_id,
            UserAssignment.user_id == user.id,
            UserAssignment.status == AssignmentStatus.ACTIVE,
            UserAssignment.valid_from <= effective_date,
            (UserAssignment.valid_until.is_(None) | (UserAssignment.valid_until >= effective_date)),
            Organization.is_active.is_(True),
            Position.is_active.is_(True),
            Position.code == WorkflowTask.required_position_code,
        )
    )
    other_task = WorkflowTask.__table__.alias("count_other_workflow_task")
    other_action = WorkflowTaskAction.__table__.alias("count_other_workflow_action")
    actor_already_participates = exists().where(
        other_task.c.instance_id == WorkflowTask.instance_id,
        other_task.c.id != WorkflowTask.id,
        or_(
            other_task.c.designated_user_id == user.id,
            exists().where(
                other_action.c.task_id == other_task.c.id,
                other_action.c.actor_id == user.id,
            ),
        ),
    )
    rows = db.execute(
        select(WorkflowInstance.target_type, func.count(WorkflowTask.id))
        .join(WorkflowTask, WorkflowTask.instance_id == WorkflowInstance.id)
        .where(
            WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
            ~actor_already_participates,
            or_(
                (
                    (WorkflowTask.assignee_mode == WorkflowAssigneeMode.DESIGNATED_USER)
                    & (WorkflowTask.designated_user_id == user.id)
                    & designated_assignment
                ),
                (
                    (WorkflowTask.assignee_mode == WorkflowAssigneeMode.SHARED_POSITION)
                    & effective_assignment
                    & (WorkflowInstance.submitted_by != user.id)
                ),
            ),
        )
        .group_by(WorkflowInstance.target_type)
    ).all()
    return {WorkflowTargetType(target_type): count for target_type, count in rows}


def awaiting_reassignment_count(db: Session) -> int:
    refresh_invalid_designated_tasks(db)
    return db.scalar(
        select(func.count(WorkflowTask.id)).where(
            WorkflowTask.status == WorkflowTaskStatus.AWAITING_REASSIGNMENT
        )
    ) or 0


def _workflow_target_for_instance(db: Session, instance: WorkflowInstance):
    return _workflow_target(db, instance.target_type, instance.target_id)


def _task_activation_status(
    db: Session,
    task: WorkflowTask,
    on_date: date,
) -> WorkflowTaskStatus:
    if task.assignee_mode != WorkflowAssigneeMode.DESIGNATED_USER:
        return WorkflowTaskStatus.ACTIVE
    assignment = _designated_task_assignment(db, task)
    if _designated_task_assignment_is_effective(task, assignment, on_date):
        return WorkflowTaskStatus.ACTIVE
    return WorkflowTaskStatus.AWAITING_REASSIGNMENT


def _resubmission_assignment(
    db: Session,
    task: WorkflowTask,
    actor: User,
    on_date: date,
) -> UserAssignment | None:
    if (
        not task.node.auto_complete_on_submit
        or actor.id != task.instance.submitted_by
        or not actor.is_active
    ):
        return None
    return next(
        (
            item
            for item in _active_assignments(
                db,
                {task.required_position_code},
                on_date,
                {actor.id},
            )
            if _assignment_has_required_scope(item)
        ),
        None,
    )


def _load_task_conflict(db: Session, task_id: int) -> WorkflowTaskConflict:
    task = db.get(WorkflowTask, task_id)
    action = db.scalar(
        select(WorkflowTaskAction)
        .where(WorkflowTaskAction.task_id == task_id)
        .order_by(WorkflowTaskAction.id.desc())
    )
    if (
        task is None
        or task.status == WorkflowTaskStatus.ACTIVE
        or action is None
    ):
        raise WorkflowValidationError(
            "workflow_task_not_active",
            "Only active workflow tasks can be completed.",
        )
    return WorkflowTaskConflict(
        actor_name=action.actor_name,
        action=action.action.value,
        completed_at=task.completed_at or action.created_at,
    )


def _load_task_conflict_after_rollback(
    db: Session,
    connection,
    task_id: int,
) -> WorkflowTaskConflict:
    with db.no_autoflush:
        task = db.get(WorkflowTask, task_id)
        if task is not None:
            db.expire(task)
        try:
            return _load_task_conflict(db, task_id)
        except WorkflowValidationError:
            if connection.dialect.name == "sqlite":
                raise
    with Session(bind=connection.engine, autoflush=False) as conflict_session:
        return _load_task_conflict(conflict_session, task_id)


def _complete_task(
    db: Session,
    task_id: int,
    actor_id: int,
    action: WorkflowAction,
    comment: str,
    completed_at: datetime,
) -> int:
    task = db.scalar(
        select(WorkflowTask)
        .where(WorkflowTask.id == task_id)
        .options(joinedload(WorkflowTask.instance), joinedload(WorkflowTask.node))
    )
    if task is None:
        raise WorkflowValidationError("workflow_task_not_found", "The workflow task does not exist.")
    if task.status != WorkflowTaskStatus.ACTIVE:
        if db.scalar(select(exists().where(WorkflowTaskAction.task_id == task.id))):
            raise _WorkflowTaskCASFailed()
        raise WorkflowValidationError(
            "workflow_task_not_active", "Only active workflow tasks can be completed."
        )
    if action not in (WorkflowAction.SUBMIT, WorkflowAction.APPROVE, WorkflowAction.RETURN):
        raise WorkflowValidationError(
            "invalid_workflow_action", "Only submit, approve and return are supported."
        )
    if action == WorkflowAction.RETURN and not task.node.allow_reject:
        raise WorkflowValidationError("workflow_return_not_allowed", "This workflow node cannot be returned.")
    actor = db.get(User, actor_id)
    enabled_superuser = bool(actor and actor.is_active and actor.is_superuser)
    if action == WorkflowAction.SUBMIT:
        assignment = (
            _resubmission_assignment(db, task, actor, completed_at.date())
            if actor
            else None
        )
    else:
        assignment = (
            _effective_task_assignment(db, task, actor, completed_at.date())
            if actor
            else None
        )
    if assignment is None and not enabled_superuser:
        raise WorkflowValidationError("workflow_task_not_actionable", "The actor is not authorized for this task.")
    actor_snapshot = _workflow_actor_snapshot(actor, assignment)

    instance = task.instance
    next_status = (
        WorkflowTaskStatus.RETURNED
        if action == WorkflowAction.RETURN
        else WorkflowTaskStatus.APPROVED
    )
    updated = db.execute(
        update(WorkflowTask)
        .where(
            WorkflowTask.id == task.id,
            WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
            WorkflowTask.version == task.version,
        )
        .values(
            status=next_status,
            completed_at=func.now(),
            version=WorkflowTask.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if updated.rowcount != 1:
        raise _WorkflowTaskCASFailed()
    returned_to_sequence = None
    target = _workflow_target_for_instance(db, instance)
    if action == WorkflowAction.RETURN:
        previous_task = db.scalar(
            select(WorkflowTask)
            .where(
                WorkflowTask.instance_id == instance.id,
                WorkflowTask.sequence < task.sequence,
            )
            .order_by(WorkflowTask.sequence.desc())
        )
        if previous_task is None:
            raise WorkflowValidationError("workflow_return_not_allowed", "The first workflow node cannot be returned.")
        previous_task.status = _task_activation_status(
            db, previous_task, completed_at.date()
        )
        previous_task.activated_at = completed_at
        previous_task.completed_at = None
        previous_task.version += 1
        db.execute(
            update(WorkflowTask)
            .where(
                WorkflowTask.instance_id == instance.id,
                WorkflowTask.sequence > task.sequence,
            )
            .values(
                status=WorkflowTaskStatus.PENDING,
                activated_at=None,
                completed_at=None,
                version=WorkflowTask.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        instance.status = WorkflowInstanceStatus.ACTIVE
        instance.completed_at = None
        instance.current_sequence = previous_task.sequence
        returned_to_sequence = previous_task.sequence
        target.status = (
            ContractStatus.REJECTED
            if previous_task.node.auto_complete_on_submit
            else ContractStatus.PENDING
        )
    else:
        next_task = db.scalar(
            select(WorkflowTask)
            .where(
                WorkflowTask.instance_id == instance.id,
                WorkflowTask.sequence > task.sequence,
            )
            .order_by(WorkflowTask.sequence)
        )
        if next_task is None:
            instance.status = WorkflowInstanceStatus.APPROVED
            instance.completed_at = completed_at
            target.status = ContractStatus.APPROVED
        else:
            next_task.status = _task_activation_status(
                db, next_task, completed_at.date()
            )
            next_task.activated_at = completed_at
            next_task.completed_at = None
            next_task.version += 1
            instance.status = WorkflowInstanceStatus.ACTIVE
            instance.completed_at = None
            instance.current_sequence = next_task.sequence
            target.status = ContractStatus.PENDING
    target.current_step = instance.current_sequence
    task_action = WorkflowTaskAction(
        task_id=task.id,
        action=action,
        actor_id=actor.id,
        actor_name=actor.full_name,
        organization_code=actor_snapshot.organization_code,
        organization_name=actor_snapshot.organization_name,
        position_code=actor_snapshot.position_code,
        position_name=actor_snapshot.position_name,
        comment=comment,
        signature_snapshot=actor.signature,
        returned_to_sequence=returned_to_sequence,
    )
    db.add(task_action)
    db.flush()
    project_contract_action(db, instance, task, task_action)
    db.flush()
    return instance.id


def complete_task(
    db: Session,
    task_id: int,
    actor: User,
    action: WorkflowAction,
    comment: str,
) -> WorkflowInstance:
    with db.no_autoflush:
        actor_id = actor.id
        connection = db.connection()
    _ensure_sqlite_outer_transaction(connection, immediate=True)
    workflow_session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    conflict = False
    try:
        instance_id = _complete_task(
            workflow_session, task_id, actor_id, WorkflowAction(action), comment, datetime.now()
        )
        workflow_session.commit()
    except _WorkflowTaskCASFailed:
        workflow_session.rollback()
        conflict = True
    except Exception:
        workflow_session.rollback()
        raise
    finally:
        workflow_session.close()

    if conflict:
        raise _load_task_conflict_after_rollback(db, connection, task_id)

    with db.no_autoflush:
        instance = db.get(WorkflowInstance, instance_id)
        _expire_parent_workflow_state(db, instance.target_type, instance.target_id)
        return db.get(WorkflowInstance, instance_id)
