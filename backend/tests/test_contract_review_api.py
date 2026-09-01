from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.core.enums import Role
from app.models.contract import Contract
from app.models.user import User
from app.services.contract_evidence import EvidenceChunk


def test_ai_review_http_returns_legacy_and_evidence_metadata():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(id=1, username="review-admin", full_name="Review Admin", hashed_password="test", is_superuser=True, is_active=True)
    contract = Contract(id=1, contract_no="CN-1", title="测试合同", party_a="甲方", party_b="乙方", amount=100, created_by=1)
    db.add_all([user, contract])
    db.commit()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    source = EvidenceChunk("3:1", 3, "合同法", "法律规范", "第一条", 1, "合同应依法履行")
    result = {
        "fact_checks": [{"claim": "付款", "verdict": "supported", "evidence": [{"title": "合同法"}]}],
        "risk_findings": [], "coverage": {"claim_count": 1, "evidence_rate": 1},
        "engine": "rule", "fallback_reason": "not_configured",
    }
    with patch("app.api.v1.endpoints.contract._contract_text_for_review", return_value=("合同正文", False)), patch(
        "app.api.v1.endpoints.contract.retrieve_evidence", return_value=[source]
    ), patch("app.api.v1.endpoints.contract.deterministic_findings", return_value=[]), patch(
        "app.api.v1.endpoints.contract.review_with_evidence", return_value=result
    ):
        response = client.post("/api/v1/contracts/1/ai-review")
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert {"markdown", "engine", "has_attachment", "kb_used", "fact_checks", "risk_findings", "retrieved_sources", "coverage", "fallback_reason"} <= body.keys()
    assert body["retrieved_sources"][0]["chunk_id"] == "3:1"
    assert body["kb_used"] == ["合同法"]
    assert client.post("/api/v1/contracts/999/ai-review").status_code == 404
    user.is_superuser = False
    user.role = Role.BUSINESS_HANDLER
    db.commit()
    assert client.post("/api/v1/contracts/1/ai-review").status_code == 403
    client.close()
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def test_attachment_review_retrieval_uses_truncated_text_and_structured_fields():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(id=2, username="review-admin-2", full_name="Review Admin", hashed_password="test", is_superuser=True, is_active=True)
    contract = Contract(
        id=2,
        contract_no="CN-2",
        title="景区酒店采购",
        party_a="甲方",
        party_b="乙方",
        amount=100,
        contract_type="酒店采购",
        subject="酒店客房",
        payment_terms="验收后付款",
        remark="重点审查",
        created_by=2,
    )
    db.add_all([user, contract])
    db.commit()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    captured: dict[str, str] = {}
    source = EvidenceChunk("4:1", 4, "酒店采购制度", "制度", "付款", 1, "验收后付款")

    def capture_query(_db, query):
        captured["query"] = query
        return [source]

    result = {
        "fact_checks": [], "risk_findings": [],
        "coverage": {"claim_count": 0, "evidence_rate": 0},
        "engine": "rule", "fallback_reason": "not_configured",
    }
    with patch("app.api.v1.endpoints.contract._contract_text_for_review", return_value=("正文" * 8000, True)), patch(
        "app.api.v1.endpoints.contract.retrieve_evidence", side_effect=capture_query
    ), patch("app.api.v1.endpoints.contract.deterministic_findings", return_value=[]), patch(
        "app.api.v1.endpoints.contract.review_with_evidence", return_value=result
    ):
        response = client.post("/api/v1/contracts/2/ai-review")
    assert response.status_code == 200, response.text
    assert len(captured["query"].split("\n【结构化合同字段】", 1)[0]) == 12000
    assert "景区酒店采购" in captured["query"]
    assert "酒店采购" in captured["query"]
    assert "酒店客房" in captured["query"]
    assert "验收后付款" in captured["query"]
    client.close()
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()
