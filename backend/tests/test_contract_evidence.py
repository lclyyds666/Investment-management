from types import SimpleNamespace

from app.services.contract_evidence import deterministic_findings, retrieve_evidence


class FakeResult:
    def __init__(self, docs):
        self.docs = docs

    def all(self):
        return self.docs


class FakeDb:
    def __init__(self, docs):
        self.docs = docs

    def scalars(self, *_args, **_kwargs):
        return FakeResult(self.docs)


def test_retrieves_later_relevant_document_not_only_first_document():
    docs = [
        SimpleNamespace(id=1, title="公司法", category="法律规范", content="无关内容 " * 500),
        SimpleNamespace(id=2, title="招标投标法", category="法律规范", content="依法必须招标的项目不得拆分规避招标。"),
    ]
    chunks = retrieve_evidence(FakeDb(docs), "本合同项目依法必须招标，不得拆分规避招标")
    assert any(chunk.title == "招标投标法" for chunk in chunks)


def test_detects_invalid_percentage_and_missing_cited_law():
    findings = deterministic_findings(
        "违约金按合同金额的120%计算。依据《不存在的管理办法》第三条。",
        {"amount": "100000"},
        [],
    )
    assert {item["code"] for item in findings} >= {"invalid_percentage", "citation_not_found"}
