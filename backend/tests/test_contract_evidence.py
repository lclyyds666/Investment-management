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


def test_supports_contract_model_field_aliases_and_caps_results():
    docs = [SimpleNamespace(id=i, title=f"制度{i}", category="法律规范", content="付款违约招标。" * 500) for i in range(1, 20)]
    chunks = retrieve_evidence(FakeDb(docs), "付款违约招标", limit=12, max_chars=12000)
    assert len(chunks) <= 12
    assert sum(len(chunk.text) for chunk in chunks) <= 12000
    findings = deterministic_findings(
        "合同编号 CN-2，甲方：乙公司。",
        {"contract_no": "CN-1", "party_a": "甲公司", "party_b": "乙公司", "amount": "100000"},
        [],
    )
    assert {item["code"] for item in findings} >= {"contract_number_mismatch", "party_mismatch", "amount_mismatch"}


def test_amount_matching_uses_decimal_and_field_context_not_substrings():
    assert not {
        item["code"]
        for item in deterministic_findings("合同金额：100.00元；第一期付款金额：50元。", {"amount": "100"}, [])
    } & {"amount_mismatch", "amount_conflict"}
    findings = deterministic_findings("合同金额：1000元。", {"amount": "100"}, [])
    assert "amount_mismatch" in {item["code"] for item in findings}


def test_checks_customer_sign_date_and_semantic_term_conflicts():
    text = (
        "客户名称：甲客户（以下简称客户）。签订日期：2026年1月2日。"
        "履行期限：2026/01/01-2026/12/31。履行期限：2027-01-01至2027-12-31。"
        "交付日期：2027-01-01。"
    )
    findings = deterministic_findings(
        text,
        {"customer_name": "乙客户", "sign_date": "2026-01-01"},
        [],
    )
    codes = {item["code"] for item in findings}
    assert {"customer_name_mismatch", "sign_date_mismatch", "term_conflict"} <= codes
    assert "date_conflict" not in codes
