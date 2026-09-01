"""Local knowledge-base evidence retrieval and deterministic contract checks."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import select

from app.models.knowledge import KnowledgeDoc


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    doc_id: int
    title: str
    category: str
    section: str
    ordinal: int
    text: str


_HEADING_RE = re.compile(r"(?m)^(?P<h>(?:第[^\n]{1,30}[章节条款]|[一二三四五六七八九十]+、|\(?[一二三四五六七八九十]+\)|\d+[.、]))[^\n]*")
_SENTENCE_RE = re.compile(r"(?<=[。！？；;.!?])\s*|\n{2,}")
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{2,}|\d+(?:\.\d+)?%?")
_PERCENT_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*%")
_LAW_RE = re.compile(r"《([^》]{2,80})》")
_NUMBER_RE = re.compile(r"\d+(?:[,.]\d+)*(?:\.\d+)?")
_DATE_RE = re.compile(r"(?P<year>20\d{2})\s*[年./-]\s*(?P<month>\d{1,2})\s*[月./-]\s*(?P<day>\d{1,2})\s*日?")
_AMOUNT_RE = re.compile(
    r"(?P<label>合同金额|合同价款|含税总价|总价|价款|(?<!付)(?<!款)(?<!期)金额)"
    r"[^\d\n]{0,20}(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>万元?|元)?"
)
_FIELD_DATE_LABELS = {
    "sign_date": ("签订日期", "签署日期", "签约日期", "签订时间", "签署时间"),
}


def _split_document(content: str) -> list[tuple[str, str]]:
    """Split by headings/paragraphs while retaining nearby section labels."""
    content = (content or "").replace("\r\n", "\n").strip()
    if not content:
        return []
    sections: list[tuple[str, str]] = []
    current = ""
    lines: list[str] = []
    for line in content.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match and lines:
            sections.append((current, "\n".join(lines).strip()))
            lines = []
        if match:
            current = line.strip()
            lines.append(line.strip())
        elif line.strip():
            lines.append(line.strip())
    if lines:
        sections.append((current, "\n".join(lines).strip()))
    if not sections:
        sections = [("", content)]
    chunks: list[tuple[str, str]] = []
    for section, block in sections:
        pieces = [p.strip() for p in _SENTENCE_RE.split(block) if p.strip()]
        if not pieces:
            continue
        # Keep chunks reasonably sized and preserve source text.
        buf = ""
        for piece in pieces:
            if buf and len(buf) + len(piece) + 1 > 900:
                chunks.append((section, buf))
                buf = ""
            buf = f"{buf}\n{piece}".strip()
        if buf:
            chunks.append((section, buf))
    return chunks


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in _TOKEN_RE.findall(text or ""):
        token = token.lower()
        if len(token) > 1:
            tokens.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            # Chinese text often has no whitespace; overlapping n-grams
            # provide stable lexical matches without an external tokenizer.
            for size in (2, 3, 4):
                tokens.update(token[i : i + size] for i in range(len(token) - size + 1))
    return tokens


def retrieve_evidence(db: Any, contract_text: str, limit: int = 12, max_chars: int = 12000) -> list[EvidenceChunk]:
    """Retrieve relevant knowledge chunks using deterministic lexical scoring."""
    if not contract_text or limit <= 0 or max_chars <= 0:
        return []
    try:
        docs: Iterable[Any] = db.scalars(select(KnowledgeDoc).order_by(KnowledgeDoc.id.asc())).all()
    except (AttributeError, TypeError):
        docs = getattr(db, "docs", [])
    query_tokens = _tokens(contract_text)
    risk_terms = _tokens("付款 违约 赔偿 管辖 招标 投资 担保 保密 知识产权 解除 终止 验收")
    candidates: list[tuple[float, EvidenceChunk]] = []
    for doc in docs:
        ordinal = 0
        for section, text in _split_document(getattr(doc, "content", "") or ""):
            ordinal += 1
            chunk_tokens = _tokens(f"{getattr(doc, 'title', '')} {section} {text}")
            overlap = len(query_tokens & chunk_tokens)
            risk_overlap = len(risk_terms & chunk_tokens & query_tokens)
            numbers = len(set(_NUMBER_RE.findall(contract_text)) & set(_NUMBER_RE.findall(text)))
            score = overlap + risk_overlap * 1.5 + numbers * 2
            if section and any(tok in section for tok in query_tokens):
                score += 2
            if score <= 0:
                continue
            chunk = EvidenceChunk(
                chunk_id=f"{getattr(doc, 'id', 0)}:{ordinal}",
                doc_id=int(getattr(doc, "id", 0)),
                title=str(getattr(doc, "title", "")),
                category=str(getattr(doc, "category", "")),
                section=section,
                ordinal=ordinal,
                text=text,
            )
            candidates.append((score, chunk))
    candidates.sort(key=lambda item: (-item[0], item[1].doc_id, item[1].ordinal))
    selected: list[EvidenceChunk] = []
    seen_docs: set[int] = set()
    total = 0
    for _, chunk in candidates:
        if len(selected) >= limit or chunk.doc_id in seen_docs:
            continue
        if total + len(chunk.text) > max_chars:
            continue
        selected.append(chunk)
        seen_docs.add(chunk.doc_id)
        total += len(chunk.text)
    # Permit multiple chunks from a document when fewer documents match.
    if len(selected) < limit:
        for _, chunk in candidates:
            if len(selected) >= limit or chunk in selected:
                continue
            if total + len(chunk.text) <= max_chars:
                selected.append(chunk)
                total += len(chunk.text)
    return selected


def _parse_decimal(value: Any) -> Decimal | None:
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return None
    multiplier = Decimal("10000") if "万" in raw else Decimal("1")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    if not raw:
        return None
    try:
        return Decimal(raw) * multiplier
    except InvalidOperation:
        return None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    match = _DATE_RE.search(str(value))
    if not match:
        return None
    try:
        return date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
    except ValueError:
        return None


def _extract_amounts(text: str) -> list[tuple[str, Decimal]]:
    values: list[tuple[str, Decimal]] = []
    for match in _AMOUNT_RE.finditer(text or ""):
        parsed = _parse_decimal(f"{match.group('value')}{match.group('unit') or ''}")
        if parsed is None:
            continue
        label = match.group("label")
        if label in {"合同金额", "合同价款"}:
            group = "contract_amount"
        elif label in {"含税总价", "总价"}:
            group = "total_amount"
        elif label == "价款":
            group = "price"
        else:
            group = "amount"
        values.append((group, parsed))
    return values


def _extract_label_values(text: str, labels: tuple[str, ...]) -> list[str]:
    if not text:
        return []
    label_pattern = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(rf"(?:{label_pattern})\s*(?:为|是|：|:)?\s*([^\n，,。；;]+)")
    values: list[str] = []
    for match in pattern.finditer(text):
        value = match.group(1).strip()
        value = re.split(r"[（(]", value, maxsplit=1)[0].strip()
        if value:
            values.append(value)
    return values


def _extract_labeled_dates(text: str, labels: tuple[str, ...]) -> list[date]:
    dates: list[date] = []
    for value in _extract_label_values(text, labels):
        parsed = _parse_date(value)
        if parsed:
            dates.append(parsed)
    return dates


def _normalise_claim(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def deterministic_findings(contract_text: str, structured_fields: dict[str, Any] | None, evidence: list[EvidenceChunk]) -> list[dict]:
    """Find obvious contradictions without invoking an LLM."""
    text = (contract_text or "")[:12000]
    fields = structured_fields or {}
    findings: list[dict] = []

    for raw in _PERCENT_RE.findall(text):
        value = float(raw)
        if value <= 0 or value > 100:
            findings.append({"code": "invalid_percentage", "claim": f"{raw}%", "verdict": "contradicted", "reason": "百分比应在0%至100%之间", "evidence_ids": []})

    cited_laws = _LAW_RE.findall(text)
    evidence_text = "\n".join(chunk.text for chunk in evidence)
    for law in cited_laws:
        if law not in evidence_text:
            findings.append({"code": "citation_not_found", "claim": f"《{law}》", "verdict": "not_found", "reason": "知识库召回片段中未找到该法规", "evidence_ids": []})

    amount_expected = fields.get("amount")
    if amount_expected not in (None, ""):
        expected_amount = _parse_decimal(amount_expected)
        extracted_amounts = _extract_amounts(text)
        if expected_amount is None or not any(value == expected_amount for _, value in extracted_amounts):
            findings.append({"code": "amount_mismatch", "claim": f"金额: {amount_expected}", "verdict": "contradicted", "reason": "结构化金额与合同正文同语义金额不一致", "evidence_ids": []})

    party_fields = (("party_a", "甲方"), ("party_b", "乙方"), ("party", "甲方"))
    for key, label in party_fields:
        expected = fields.get(key)
        if expected in (None, ""):
            continue
        labels = (label,) if key != "party" else ("甲方", "乙方")
        actual_values = _extract_label_values(text, labels)
        expected_norm = _normalise_claim(expected)
        if not any(_normalise_claim(value) == expected_norm for value in actual_values):
            findings.append({"code": "party_mismatch", "claim": f"{label}: {expected}", "verdict": "contradicted", "reason": "结构化主体与合同正文同标签主体不一致", "evidence_ids": []})

    contract_no = fields.get("contract_no") or fields.get("contract_number")
    if contract_no not in (None, ""):
        escaped = re.escape(str(contract_no).strip())
        if not re.search(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", text, flags=re.I):
            findings.append({"code": "contract_number_mismatch", "claim": f"合同编号: {contract_no}", "verdict": "contradicted", "reason": "结构化合同编号未在合同正文中精确出现", "evidence_ids": []})

    customer = fields.get("customer_name")
    if customer not in (None, ""):
        customer_values = _extract_label_values(text, ("客户名称", "客户"))
        if not any(_normalise_claim(value) == _normalise_claim(customer) for value in customer_values):
            findings.append({"code": "customer_name_mismatch", "claim": f"客户名称: {customer}", "verdict": "contradicted", "reason": "结构化客户名称与合同正文同标签客户不一致", "evidence_ids": []})

    sign_date = fields.get("sign_date")
    if sign_date not in (None, ""):
        expected_date = _parse_date(sign_date)
        actual_dates = _extract_labeled_dates(text, _FIELD_DATE_LABELS["sign_date"])
        if expected_date is None or not any(value == expected_date for value in actual_dates):
            findings.append({"code": "sign_date_mismatch", "claim": f"签订日期: {sign_date}", "verdict": "contradicted", "reason": "结构化签订日期与合同正文签署日期不一致", "evidence_ids": []})

    grouped_amounts: dict[str, set[Decimal]] = {}
    for group, value in _extract_amounts(text):
        grouped_amounts.setdefault(group, set()).add(value)
    if any(len(values) > 1 for values in grouped_amounts.values()):
        findings.append({"code": "amount_conflict", "claim": "合同同一金额字段存在多个值", "verdict": "contradicted", "reason": "同一语义金额字段出现相互冲突的重复信息", "evidence_ids": []})

    sign_dates = _extract_labeled_dates(text, _FIELD_DATE_LABELS["sign_date"])
    if len(set(sign_dates)) > 1:
        findings.append({"code": "date_conflict", "claim": "合同同一签订日期存在多个值", "verdict": "contradicted", "reason": "同一语义签订日期字段出现相互冲突的重复信息", "evidence_ids": []})
    term_values = _extract_label_values(text, ("履行期限", "服务期限", "合同期限", "有效期", "期限"))
    if len({_normalise_claim(value) for value in term_values}) > 1:
        findings.append({"code": "term_conflict", "claim": "合同同一期限存在多个值", "verdict": "contradicted", "reason": "同一语义期限字段出现相互冲突的重复信息", "evidence_ids": []})

    term_expected = next((fields.get(key) for key in ("term", "duration", "performance_period", "validity_period", "期限", "履行期限") if fields.get(key) not in (None, "")), None)
    if term_expected not in (None, ""):
        term_values = _extract_label_values(text, ("履行期限", "服务期限", "合同期限", "有效期", "期限"))
        if not any(_normalise_claim(value) == _normalise_claim(term_expected) for value in term_values):
            findings.append({"code": "term_mismatch", "claim": f"期限: {term_expected}", "verdict": "contradicted", "reason": "结构化期限与合同正文同标签期限不一致", "evidence_ids": []})
    return findings
