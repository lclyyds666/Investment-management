import unittest
from datetime import date

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.init_db  # noqa: F401
from app.api.deps import get_current_user
from app.api.v1.endpoints.contract import eligible_contracts
from app.core.enums import AssignmentStatus, ContractStatus, InvoiceSourceKind
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.contract import Contract
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.schemas.contract import ContractCreate, ContractUpdate
from app.services.organization_catalog import seed_authorization_catalog


class ContractBusinessScopeTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        creator = User(
            username="contract-scope-creator",
            full_name="合同经办",
            hashed_password="test",
            is_active=True,
        )
        self.db.add(creator)
        self.db.flush()

        self.approved_ticket_contract = self._add_contract(
            creator.id,
            "HT-TICKET",
            ContractStatus.APPROVED,
            "changsha-dongqu",
            ["ticket"],
        )
        self._add_contract(
            creator.id,
            "HT-HOTEL",
            ContractStatus.APPROVED,
            "changsha-dongqu",
            ["hotel"],
        )
        self._add_contract(
            creator.id,
            "HT-OTHER-SCENIC",
            ContractStatus.APPROVED,
            "guanquelou",
            ["ticket", "hotel"],
        )
        self._add_contract(
            creator.id,
            "HT-PENDING",
            ContractStatus.PENDING,
            "changsha-dongqu",
            ["ticket"],
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _add_contract(
        self,
        creator_id: int,
        contract_no: str,
        status: ContractStatus,
        scenic_id: str,
        business_scopes: list[str],
    ) -> Contract:
        contract = Contract(
            contract_no=contract_no,
            title=contract_no,
            status=status,
            scenic_id=scenic_id,
            business_scopes=business_scopes,
            created_by=creator_id,
            company_code="investment",
            organization_code="investment.general",
        )
        self.db.add(contract)
        self.db.flush()
        return contract

    def test_new_contract_requires_one_scenic_and_business_scope(self):
        with self.assertRaises(ValidationError):
            ContractCreate(
                contract_no="HT-EMPTY-SCENIC",
                title="测试",
                scenic_id="",
                business_scopes=["ticket"],
            )

        with self.assertRaises(ValidationError):
            ContractCreate(
                contract_no="HT-1",
                title="测试",
                scenic_id="",
                business_scopes=[],
            )

        with self.assertRaises(ValidationError):
            ContractCreate(
                contract_no="HT-2",
                title="测试",
                scenic_id="guanquelou",
                business_scopes=["retail"],
            )

    def test_business_scopes_are_deduplicated(self):
        contract = ContractCreate(
            contract_no="HT-3",
            title="测试",
            scenic_id="guanquelou",
            business_scopes=["ticket", "hotel", "ticket"],
        )

        self.assertEqual(contract.business_scopes, ["ticket", "hotel"])

    def test_update_cannot_clear_required_linkage_fields(self):
        with self.assertRaises(ValidationError):
            ContractUpdate(scenic_id=None)

        with self.assertRaises(ValidationError):
            ContractUpdate(business_scopes=None)

    def test_eligible_contract_requires_approved_matching_scope(self):
        result = eligible_contracts(
            self.db,
            "changsha-dongqu",
            InvoiceSourceKind.TICKET,
        )

        self.assertEqual(
            [row.id for row in result],
            [self.approved_ticket_contract.id],
        )

    def test_eligible_contract_applies_visibility_predicate(self):
        result = eligible_contracts(
            self.db,
            "changsha-dongqu",
            InvoiceSourceKind.TICKET,
            Contract.id != self.approved_ticket_contract.id,
        )

        self.assertEqual(result, [])


class ContractBusinessScopeApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.contract_user = self._add_user("contract-options-user")
        hidden_owner = self._add_user("hidden-contract-owner")
        self.denied_user = self._add_user("denied-contract-user")
        self.db.flush()
        self.db.add(UserAssignment(
            user_id=self.contract_user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == "investment.general")
            ),
            position_id=self.db.scalar(
                select(Position.id).where(
                    Position.code == "investment.department.junior_manager"
                )
            ),
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        ))
        self.visible_contract = Contract(
            contract_no="HTTP-VISIBLE",
            title="可见合同",
            status=ContractStatus.APPROVED,
            scenic_id="guanquelou",
            business_scopes=["ticket"],
            created_by=self.contract_user.id,
            company_code="investment",
            organization_code="investment.general",
        )
        self.hidden_contract = Contract(
            contract_no="HTTP-HIDDEN",
            title="不可见合同",
            status=ContractStatus.APPROVED,
            scenic_id="guanquelou",
            business_scopes=["ticket"],
            created_by=hidden_owner.id,
            company_code="investment",
            organization_code="investment.asset_finance",
        )
        self.db.add_all([self.visible_contract, self.hidden_contract])
        self.db.commit()
        self.current_user = {"value": self.denied_user}
        self.app = create_app()
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user["value"]
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def _add_user(self, username: str) -> User:
        user = User(
            username=username,
            full_name=username,
            hashed_password="test",
            is_active=True,
        )
        self.db.add(user)
        return user

    def test_eligible_endpoint_requires_permission_and_applies_visibility(self):
        denied = self.client.get(
            "/api/v1/contracts/eligible",
            params={"scenic_id": "guanquelou", "source_kind": "ticket"},
        )
        self.assertEqual(denied.status_code, 403)

        self.current_user["value"] = self.contract_user
        allowed = self.client.get(
            "/api/v1/contracts/eligible",
            params={"scenic_id": "guanquelou", "source_kind": "ticket"},
        )

        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(
            [item["id"] for item in allowed.json()["data"]],
            [self.visible_contract.id],
        )

    def test_contract_user_reads_safe_scenic_options_without_rate_access(self):
        denied_options = self.client.get("/api/v1/scenic-spots/options")
        self.assertEqual(denied_options.status_code, 403)

        self.current_user["value"] = self.contract_user

        full_config = self.client.get("/api/v1/scenic-spots/configs")
        safe_options = self.client.get("/api/v1/scenic-spots/options")

        self.assertEqual(full_config.status_code, 403)
        self.assertEqual(safe_options.status_code, 200, safe_options.text)
        self.assertTrue(safe_options.json()["data"])
        self.assertEqual(
            set(safe_options.json()["data"][0]),
            {"scenic_id", "scenic_name"},
        )


if __name__ == "__main__":
    unittest.main()
