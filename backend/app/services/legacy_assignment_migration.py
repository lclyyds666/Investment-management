from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AssignmentStatus, CompanyCode, Role
from app.models.organization import ExternalAssignment, Organization, Position, UserAssignment
from app.models.portal import UserCompanyRole
from app.models.user import User


@dataclass(frozen=True)
class LegacyTarget:
    organization_code: str
    position_code: str
    external: bool = False


LEGACY_TARGETS = {
    Role.BUSINESS_HANDLER: LegacyTarget("supplymanagement", "supply.business_handler"),
    Role.BUSINESS_REVIEWER: LegacyTarget("supplymanagement", "supply.business_reviewer"),
    Role.FINANCE_HANDLER: LegacyTarget("supplymanagement", "supply.finance_handler"),
    Role.SCM_DIRECTOR: LegacyTarget("supplymanagement", "supply.company_leader"),
    Role.INVEST_DIRECTOR: LegacyTarget("supplymanagement", "governance.supply_leader"),
    Role.RISK_AUDITOR: LegacyTarget("investment.legal_risk", "investment.duty.supply_risk_review"),
    Role.FINANCE_REVIEWER: LegacyTarget("investment.asset_finance", "investment.duty.supply_finance_review"),
    Role.LEGAL_COUNSEL: LegacyTarget("external.legal", "external.legal_counsel", external=True),
}


def legacy_target(role: Role) -> LegacyTarget | None:
    return LEGACY_TARGETS.get(role)


class MigrationIssue(BaseModel):
    user_id: int
    username: str
    legacy_role: str
    reason: str


class MigrationRow(BaseModel):
    user_id: int
    username: str
    legacy_role: str
    organization_code: str | None = None
    position_code: str | None = None


class MigrationReport(BaseModel):
    created: int = 0
    created_rows: list[MigrationRow] = Field(default_factory=list)
    existing: int = 0
    existing_rows: list[MigrationRow] = Field(default_factory=list)
    unresolved: list[MigrationIssue] = Field(default_factory=list)
    skipped_admin: int = 0
    skipped_admin_rows: list[MigrationRow] = Field(default_factory=list)
    skipped_unassigned: int = 0
    skipped_unassigned_rows: list[MigrationRow] = Field(default_factory=list)


def _legacy_role(db: Session, user: User) -> Role:
    company_role = db.scalar(select(UserCompanyRole).where(
        UserCompanyRole.user_id == user.id,
        UserCompanyRole.company_code == CompanyCode.SUPPLY_MANAGEMENT.value,
    ))
    return company_role.role if company_role is not None else user.role


def _issue(report: MigrationReport, user: User, role: Role, reason: str) -> None:
    report.unresolved.append(MigrationIssue(
        user_id=user.id, username=user.username, legacy_role=role.value, reason=reason,
    ))


def _row(user: User, role: Role, target: LegacyTarget | None = None) -> MigrationRow:
    return MigrationRow(
        user_id=user.id,
        username=user.username,
        legacy_role=role.value,
        organization_code=target.organization_code if target else None,
        position_code=target.position_code if target else None,
    )


def migrate_legacy_assignments(db: Session, dry_run: bool) -> MigrationReport:
    """Translate legacy roles without changing legacy data or overwriting assignments."""
    report = MigrationReport()
    pending_assignments: list[UserAssignment] = []
    try:
        with db.no_autoflush if dry_run else nullcontext():
            for user in db.scalars(select(User).order_by(User.id)):
                if user.is_superuser:
                    report.skipped_admin += 1
                    report.skipped_admin_rows.append(_row(user, user.role))
                    continue
                role = _legacy_role(db, user)
                if role == Role.UNASSIGNED:
                    report.skipped_unassigned += 1
                    report.skipped_unassigned_rows.append(_row(user, role))
                    continue
                target = legacy_target(role)
                if target is None:
                    _issue(report, user, role, "No normalized position mapping exists for this legacy role.")
                    continue
                organization = db.scalar(select(Organization).where(Organization.code == target.organization_code))
                position = db.scalar(select(Position).where(Position.code == target.position_code))
                if organization is None or position is None:
                    missing = "organization" if organization is None else "position"
                    _issue(report, user, role, f"Required normalized {missing} code is missing from the catalog.")
                    continue
                existing = db.scalar(select(UserAssignment).where(
                    UserAssignment.user_id == user.id,
                    UserAssignment.organization_id == organization.id,
                    UserAssignment.position_id == position.id,
                ))
                if existing is not None:
                    report.existing += 1
                    report.existing_rows.append(_row(user, role, target))
                    continue
                assignment = UserAssignment(
                    user_id=user.id, organization_id=organization.id, position_id=position.id,
                    valid_from=date.today(), status=AssignmentStatus.ACTIVE, source="legacy",
                )
                report.created += 1
                report.created_rows.append(_row(user, role, target))
                if not dry_run:
                    db.add(assignment)
                    pending_assignments.append(assignment)
                if target.external:
                    _issue(report, user, role, "External legal counsel effective end date requires administrator confirmation.")

        if dry_run:
            return report
        if report.unresolved and any("Required normalized" in issue.reason for issue in report.unresolved):
            db.rollback()
            return report
        db.flush()
        for assignment in pending_assignments:
            if assignment.position.code == "external.legal_counsel":
                db.add(ExternalAssignment(
                    assignment_id=assignment.id, provider_name="", service_scopes=["contract_legal_review"],
                ))
        db.commit()
        return report
    except Exception:
        if not dry_run:
            db.rollback()
        raise
