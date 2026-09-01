from types import SimpleNamespace

from app.services import contract_review_llm
from app.services.contract_evidence import EvidenceChunk
from app.services.contract_review import render_review_markdown


def _response(payload):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=__import__('json').dumps(payload, ensure_ascii=False)))])


class _FakeCompletions:
    def __init__(self, response):
        self.response = response

    def create(self, **kwargs):
        return self.response


class _FakeOpenAI:
    response = None

    def __init__(self, **kwargs):
        self.chat = SimpleNamespace(completions=_FakeCompletions(self.response))


def test_invalid_model_evidence_id_becomes_not_found(monkeypatch):
    _FakeOpenAI.response = _response({"fact_checks": [{"claim": "依据公司法", "verdict": "supported", "evidence_ids": ["999:1"]}], "risk_findings": []})
    monkeypatch.setattr(contract_review_llm, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(contract_review_llm.settings, "DEEPSEEK_API_KEY", "test")
    result = contract_review_llm.review_with_evidence(
        "依据公司法", {}, [EvidenceChunk("1:1", 1, "公司法", "法规", "第一条", 1, "公司法第一条")], []
    )
    assert result["fact_checks"][0]["verdict"] == "not_found"
    assert result["fact_checks"][0]["evidence"] == []


def test_deepseek_failure_preserves_deterministic_findings(monkeypatch):
    class Failing:
        def __init__(self, **kwargs):
            raise TimeoutError("timeout")

    monkeypatch.setattr(contract_review_llm, "OpenAI", Failing)
    monkeypatch.setattr(contract_review_llm.settings, "DEEPSEEK_API_KEY", "test")
    result = contract_review_llm.review_with_evidence("违约金 120%", {}, [], [{"code": "invalid_percentage", "claim": "120%", "verdict": "contradicted"}])
    assert result["engine"] == "rule"
    assert result["fallback_reason"] == "provider_error"
    assert result["fact_checks"][0]["code"] == "invalid_percentage"


def test_invalid_schema_falls_back_without_deepseek_engine(monkeypatch):
    _FakeOpenAI.response = _response({})
    monkeypatch.setattr(contract_review_llm, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(contract_review_llm.settings, "DEEPSEEK_API_KEY", "test")
    result = contract_review_llm.review_with_evidence(
        "合同正文", {}, [], [{"code": "invalid_percentage", "claim": "120%", "verdict": "contradicted"}]
    )
    assert result["engine"] == "rule"
    assert result["fallback_reason"] == "invalid_response"
    assert result["fact_checks"][0]["verdict"] == "contradicted"


def test_untrusted_contract_quote_is_not_presented_as_verified_text(monkeypatch):
    _FakeOpenAI.response = _response({
        "fact_checks": [{
            "code": "payment_risk",
            "claim": "付款风险",
            "verdict": "not_found",
            "contract_quote": "模型编造的合同原文",
            "evidence_ids": [],
        }],
        "risk_findings": [],
    })
    monkeypatch.setattr(contract_review_llm, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(contract_review_llm.settings, "DEEPSEEK_API_KEY", "test")
    result = contract_review_llm.review_with_evidence("真实合同文本", {}, [], [])
    item = result["fact_checks"][0]
    assert item["contract_quote"] == ""
    assert item["model_quote"] == "模型编造的合同原文"


def test_coverage_includes_risk_findings_and_deterministic_item_replaces_duplicate(monkeypatch):
    _FakeOpenAI.response = _response({
        "fact_checks": [{
            "code": "invalid_percentage",
            "claim": "违约金120%",
            "verdict": "not_found",
            "evidence_ids": [],
        }],
        "risk_findings": [{
            "code": "payment_risk",
            "claim": "付款条件",
            "verdict": "supported",
            "evidence_ids": ["1:1"],
        }],
    })
    monkeypatch.setattr(contract_review_llm, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(contract_review_llm.settings, "DEEPSEEK_API_KEY", "test")
    result = contract_review_llm.review_with_evidence(
        "违约金120%", {}, [EvidenceChunk("1:1", 1, "合同法", "法规", "第一条", 1, "付款应验收")],
        [{"code": "invalid_percentage", "claim": "违约金120%", "verdict": "contradicted"}],
    )
    assert len(result["fact_checks"]) == 1
    assert result["fact_checks"][0]["verdict"] == "contradicted"
    assert result["coverage"]["claim_count"] == 2
    assert result["coverage"]["evidence_rate"] == 0.5


def test_fallback_markdown_does_not_claim_no_risk_when_no_findings():
    markdown = render_review_markdown({
        "fact_checks": [],
        "risk_findings": [],
        "coverage": {"claim_count": 0, "evidence_rate": 0},
        "fallback_reason": "provider_error",
    })
    assert "不能据此认定合同无风险" in markdown
    assert "未发现可核验的风险主张" not in markdown
