"""Local knowledge-base evidence retrieval and deterministic contract checks."""
from __future__ import annotations

import re
from dataclasses import dataclass
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


def deterministic_findings(contract_text: str, structured_fields: dict[str, Any] | None, evidence: list[EvidenceChunk]) -> list[dict]:
    """Find obvious contradictions without invoking an LLM."""
    text = contract_text or ""
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

    checks = (
        (("amount",), "amount_mismatch", "金额"),
        (("party", "party_a", "party_b"), "party_mismatch", "主体"),
        (("contract_number", "contract_no"), "contract_number_mismatch", "合同编号"),
    )
    for keys, code, label in checks:
        expected_values = [fields.get(key) for key in keys if fields.get(key) not in (None, "")]
        for expected in expected_values:
            expected_s = str(expected)
            # Decimal and formatted currency representations are compared
            # both literally and by their digit sequence.
            normalized_expected = re.sub(r"[^\d.]", "", expected_s)
            normalized_text = re.sub(r"[^\d.]", "", text)
            if expected_s in text or (normalized_expected and normalized_expected in normalized_text):
                continue
            findings.append({"code": code, "claim": f"{label}: {expected_s}", "verdict": "contradicted", "reason": "结构化字段与合同正文不一致", "evidence_ids": []})

    for label, pattern, code in (("金额", r"(?:金额|价款|总价)[^\d]{0,12}(\d[\d,.]*)", "amount_conflict"), ("日期", r"(20\d{2}[年/-]\d{1,2}[月/-]\d{1,2}日?)", "date_conflict")):
        values = pattern and re.findall(pattern, text)
        unique = set(values)
        if len(unique) > 1:
            findings.append({"code": code, "claim": f"合同内{label}存在多个值", "verdict": "contradicted", "reason": "同一合同中出现相互冲突的重复信息", "evidence_ids": []})
    return findings
