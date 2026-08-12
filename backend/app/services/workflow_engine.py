from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import exists, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.enums import (
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
from app.models.approval_form import ApprovalForm
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


WORKFLOW_CODE_BY_TARGET = {
    WorkflowTargetType.CONTRACT: "supply.contract.v2",
    WorkflowTargetType.PAYMENT_APPROVAL: "supply.payment.v2",
    WorkflowTargetType.BUSINESS_APPROVAL: "supply.business.v2",
}


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

    candidates: list[WorkflowCandidate] = []
    seen_users: set[int] = set()
    for assignment in _active_assignments(db, {node.position_code}, on_date):
        if assignment.user_id in seen_users or not _assignment_has_required_scope(assignment):
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


def _ensure_sqlite_outer_transaction(connection) -> None:
    if connection.dialect.name != "sqlite":
        return
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN")


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
    submitter_id: int,
    designated_users: dict[str, int],
    submitted_on: date,
) -> tuple[UserAssignment, dict[str, UserAssignment]]:
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
    if submit_assignment is None:
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
        submitter_id,
        designated_users,
        submitted_at.date(),
    )
    submitter = submit_assignment.user
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
    db.add(WorkflowTaskAction(
        task_id=submit_task.id,
        action=WorkflowAction.SUBMIT,
        actor_id=submitter_id,
        actor_name=submitter.full_name,
        organization_code=submit_assignment.organization.code,
        organization_name=submit_assignment.organization.name,
        position_code=submit_assignment.position.code,
        position_name=submit_assignment.position.name,
        signature_snapshot=submitter.signature,
    ))
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
    if not user.is_active or task.status != WorkflowTaskStatus.ACTIVE:
        return None
    if _actor_has_other_workflow_role(db, task, user.id):
        return None
    if task.assignee_mode == WorkflowAssigneeMode.DESIGNATED_USER:
        assignment = db.scalar(
            select(UserAssignment)
            .where(UserAssignment.id == task.designated_assignment_id)
            .options(
                joinedload(UserAssignment.organization),
                joinedload(UserAssignment.position),
                joinedload(UserAssignment.external_detail),
            )
        )
        if not _task_assignment_is_effective(task, assignment, user, on_date):
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
        return assignment

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
        if task.designated_user is None or not _task_assignment_is_effective(
            task, task.designated_assignment, task.designated_user, effective_date
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


def _workflow_target_for_instance(db: Session, instance: WorkflowInstance):
    return _workflow_target(db, instance.target_type, instance.target_id)


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
        .with_for_update()
    )
    if task is None:
        raise WorkflowValidationError("workflow_task_not_found", "The workflow task does not exist.")
    if task.status != WorkflowTaskStatus.ACTIVE:
        raise WorkflowValidationError("workflow_task_not_active", "Only active workflow tasks can be completed.")
    if action not in (WorkflowAction.APPROVE, WorkflowAction.RETURN):
        raise WorkflowValidationError("invalid_workflow_action", "Only approve and return are supported.")
    if action == WorkflowAction.RETURN and not task.node.allow_reject:
        raise WorkflowValidationError("workflow_return_not_allowed", "This workflow node cannot be returned.")
    actor = db.get(User, actor_id)
    assignment = _effective_task_assignment(db, task, actor, completed_at.date()) if actor else None
    if assignment is None:
        raise WorkflowValidationError("workflow_task_not_actionable", "The actor is not authorized for this task.")

    instance = task.instance
    task.status = WorkflowTaskStatus.APPROVED if action == WorkflowAction.APPROVE else WorkflowTaskStatus.RETURNED
    task.completed_at = completed_at
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
            .with_for_update()
        )
        if previous_task is None:
            raise WorkflowValidationError("workflow_return_not_allowed", "The first workflow node cannot be returned.")
        previous_task.status = WorkflowTaskStatus.ACTIVE
        previous_task.activated_at = completed_at
        previous_task.completed_at = None
        instance.current_sequence = previous_task.sequence
        returned_to_sequence = previous_task.sequence
    else:
        next_task = db.scalar(
            select(WorkflowTask)
            .where(
                WorkflowTask.instance_id == instance.id,
                WorkflowTask.sequence > task.sequence,
            )
            .order_by(WorkflowTask.sequence)
            .with_for_update()
        )
        if next_task is None:
            instance.status = WorkflowInstanceStatus.APPROVED
            instance.completed_at = completed_at
            target.status = ContractStatus.APPROVED
        else:
            next_task.status = WorkflowTaskStatus.ACTIVE
            next_task.activated_at = completed_at
            instance.current_sequence = next_task.sequence
    target.current_step = instance.current_sequence
    db.add(WorkflowTaskAction(
        task_id=task.id,
        action=action,
        actor_id=actor.id,
        actor_name=actor.full_name,
        organization_code=assignment.organization.code,
        organization_name=assignment.organization.name,
        position_code=assignment.position.code,
        position_name=assignment.position.name,
        comment=comment,
        signature_snapshot=actor.signature,
        returned_to_sequence=returned_to_sequence,
    ))
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
    _ensure_sqlite_outer_transaction(connection)
    workflow_session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        instance_id = _complete_task(
            workflow_session, task_id, actor_id, WorkflowAction(action), comment, datetime.now()
        )
        workflow_session.commit()
    except Exception:
        workflow_session.rollback()
        raise
    finally:
        workflow_session.close()

    instance = db.get(WorkflowInstance, instance_id)
    _expire_parent_workflow_state(db, instance.target_type, instance.target_id)
    with db.no_autoflush:
        return db.get(WorkflowInstance, instance_id)
