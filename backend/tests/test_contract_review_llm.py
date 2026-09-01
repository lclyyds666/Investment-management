from types import SimpleNamespace

from app.services import contract_review_llm
from app.services.contract_evidence import EvidenceChunk


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
    _FakeOpenAI.response = _response({"fact_checks": [{"claim": "依据公司法", "verdict": "supported", "evidence_ids": ["999:1"]}]})
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

