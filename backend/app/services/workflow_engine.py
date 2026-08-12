from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.enums import AssignmentStatus, WorkflowAssigneeMode, WorkflowVersionStatus
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.models.workflow import WorkflowDefinition, WorkflowNode, WorkflowVersion
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
    if connection.dialect.name == "sqlite" and not connection.in_nested_transaction():
        connection.exec_driver_sql("BEGIN")
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


def _expire_parent_catalog_state(db: Session) -> None:
    catalog_types = (WorkflowDefinition, WorkflowVersion, WorkflowNode)
    with db.no_autoflush:
        for instance in list(db.identity_map.values()):
            if isinstance(instance, catalog_types):
                db.expire(instance)
