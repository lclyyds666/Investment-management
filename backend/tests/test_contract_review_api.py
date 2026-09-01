from types import SimpleNamespace
from unittest.mock import patch

from app.api.v1.endpoints.contract import ai_review_contract
from app.services.contract_evidence import EvidenceChunk


def test_ai_review_returns_evidence_metadata():
    contract = SimpleNamespace(
        id=1,
        contract_no="CN-1",
        title="测试合同",
        party_a="甲方",
        party_b="乙方",
        amount=100,
        sign_date=None,
        contract_type="采购",
        customer_name="客户",
        subject="服务",
        currency="人民币",
        payment_terms="一次性付款",
        remark="",
        is_internal=False,
    )
    source = EvidenceChunk("3:1", 3, "合同法", "法律规范", "第一条", 1, "合同应依法履行")
    structured = {"contract_no": "CN-1"}
    result = {
        "fact_checks": [{"claim": "付款", "verdict": "supported", "evidence": [{"title": "合同法"}]}],
        "risk_findings": [],
        "coverage": {"claim_count": 1, "evidence_rate": 1},
        "engine": "rule",
        "fallback_reason": "not_configured",
    }
    with patch("app.api.v1.endpoints.contract._get_contract_or_404", return_value=contract), patch(
        "app.api.v1.endpoints.contract._ensure_contract_visible"
    ), patch(
        "app.api.v1.endpoints.contract._contract_text_for_review", return_value=("合同正文", False)
    ), patch(
        "app.api.v1.endpoints.contract.retrieve_evidence", return_value=[source]
    ), patch(
        "app.api.v1.endpoints.contract.deterministic_findings", return_value=[]
    ) as deterministic, patch(
        "app.api.v1.endpoints.contract.review_with_evidence", return_value=result
    ) as review:
        response = ai_review_contract(1, db=SimpleNamespace(), current_user=SimpleNamespace())

    body = response.data
    assert {"fact_checks", "risk_findings", "retrieved_sources", "coverage", "fallback_reason"} <= body.keys()
    assert body["retrieved_sources"][0]["chunk_id"] == "3:1"
    assert body["kb_used"] == ["合同法"]
    deterministic.assert_called_once()
    review.assert_called_once_with("合同正文", structured | {
        "title": "测试合同", "party_a": "甲方", "party_b": "乙方", "amount": "100",
        "sign_date": "", "contract_type": "采购", "customer_name": "客户", "subject": "服务",
        "currency": "人民币", "payment_terms": "一次性付款", "remark": "", "is_internal": False,
    }, [source], [])
