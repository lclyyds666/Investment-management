"""Structured DeepSeek contract review with server-side evidence validation."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings
from app.services.contract_evidence import EvidenceChunk

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency in local tooling
    OpenAI = None  # type: ignore[assignment,misc]

logger = logging.getLogger("app.contract_review_llm")

_VERDICTS = {"supported", "contradicted", "not_found", "not_applicable"}
_RISK_LEVELS = {"high", "medium", "low"}


def _evidence_dict(chunk: EvidenceChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "title": chunk.title,
        "category": chunk.category,
        "section": chunk.section,
        "ordinal": chunk.ordinal,
        "text": chunk.text,
    }


def _parse_json(content: Any) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ValueError("invalid_response")
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_response") from exc
    if not isinstance(parsed, dict):
        raise ValueError("invalid_response")
    if not isinstance(parsed.get("fact_checks"), list) or not isinstance(parsed.get("risk_findings"), list):
        raise ValueError("invalid_response")
    return parsed


def _normalise_item(
    item: Any,
    evidence_map: dict[str, EvidenceChunk],
    risk: bool = False,
    contract_text: str = "",
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    claim = str(item.get("claim") or item.get("title") or "").strip()
    if not claim:
        return None
    verdict = str(item.get("verdict") or "not_found").lower()
    if verdict not in _VERDICTS:
        verdict = "not_found"
    level = str(item.get("risk_level") or "medium").lower()
    if level not in _RISK_LEVELS:
        level = "medium"
    ids = item.get("evidence_ids")
    if not isinstance(ids, list):
        ids = []
    valid_ids = [str(chunk_id) for chunk_id in ids if str(chunk_id) in evidence_map]
    # A knowledge-base assertion without a server-verified source is unproven.
    if not valid_ids and verdict in {"supported", "contradicted"}:
        verdict = "not_found"
    raw_quote = str(item.get("contract_quote") or "").strip()
    contract_quote = raw_quote if raw_quote and raw_quote in (contract_text or "") else ""
    result: dict[str, Any] = {
        "code": str(item.get("code") or "").strip(),
        "claim": claim,
        "verdict": verdict,
        "reason": str(item.get("reason") or "").strip(),
        "contract_quote": contract_quote,
        "evidence_ids": valid_ids,
        "evidence": [_evidence_dict(evidence_map[chunk_id]) for chunk_id in valid_ids],
        "risk_level": level,
        "suggestion": str(item.get("suggestion") or "").strip(),
    }
    if raw_quote and not contract_quote:
        result["model_quote"] = raw_quote
    if risk:
        result["title"] = claim
    return result


def _claim_key(item: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", str(item.get("claim") or "").strip()).lower()


def _finding_key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("code") or "").strip().lower(), _claim_key(item)


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for item in items:
        code, claim = _finding_key(item)
        key = (code, claim)
        if key in seen_keys or (not code and any(existing_claim == claim for _, existing_claim in seen_keys if claim)):
            continue
        result.append(item)
        seen_keys.add(key)
    return result


def _merge_findings(
    items: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    evidence_map: dict[str, EvidenceChunk],
    contract_text: str = "",
) -> list[dict[str, Any]]:
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        code = str(finding.get("code") or "deterministic_check")
        claim = str(finding.get("claim") or code)
        item = _normalise_item(
            {**finding, "code": code, "claim": claim, "evidence_ids": finding.get("evidence_ids", [])},
            evidence_map,
            contract_text=contract_text,
        )
        if item is None:
            continue
        # Deterministic checks are authoritative local validations and do not
        # require a knowledge-base citation to remain contradicted.
        deterministic_verdict = str(finding.get("verdict") or "").lower()
        if deterministic_verdict in _VERDICTS:
            item["verdict"] = deterministic_verdict
        item["code"] = code
        matching_index = next(
            (index for index, existing_item in enumerate(items)
             if _finding_key(existing_item) == _finding_key(item)
             or (not str(existing_item.get("code") or "").strip() and _claim_key(existing_item) == _claim_key(item))),
            None,
        )
        if matching_index is None:
            items.append(item)
        else:
            existing_item = items[matching_index]
            if not item.get("reason"):
                item["reason"] = existing_item.get("reason", "")
            if not item.get("suggestion"):
                item["suggestion"] = existing_item.get("suggestion", "")
            items[matching_index] = item
    return items


def _coverage(fact_checks: list[dict[str, Any]], risk_findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    all_items = [*fact_checks, *(risk_findings or [])]
    count = len(all_items)
    supported = sum(item["verdict"] == "supported" for item in all_items)
    contradicted = sum(item["verdict"] == "contradicted" for item in all_items)
    not_found = sum(item["verdict"] == "not_found" for item in all_items)
    evidenced = sum(bool(item.get("evidence")) for item in all_items)
    return {
        "claim_count": count,
        "supported_count": supported,
        "contradicted_count": contradicted,
        "not_found_count": not_found,
        "evidence_rate": round(evidenced / count, 2) if count else 0,
    }


def _fallback(contract_text: str, evidence: list[EvidenceChunk], findings: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    evidence_map = {chunk.chunk_id: chunk for chunk in evidence}
    fact_checks = _merge_findings([], findings, evidence_map, contract_text=contract_text)
    return {
        "fact_checks": fact_checks,
        "risk_findings": [],
        "coverage": _coverage(fact_checks, []),
        "engine": "rule",
        "fallback_reason": reason,
    }


def review_with_evidence(
    contract_text: str,
    structured_fields: dict[str, Any] | None,
    evidence: list[EvidenceChunk],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Call DeepSeek with retrieved evidence, then validate every citation."""
    evidence_map = {chunk.chunk_id: chunk for chunk in evidence}
    if not (contract_text or "").strip():
        return _fallback(contract_text, evidence, findings, "no_text")
    if not settings.AI_ENABLED or OpenAI is None:
        return _fallback(contract_text, evidence, findings, "not_configured")
    source_payload = [_evidence_dict(chunk) for chunk in evidence]
    system_prompt = (
        "你是代表我方利益的合同法务审查专家。只依据用户合同、结构化字段和给定证据，禁止臆造法规。"
        "必须返回严格 JSON 对象，不要 Markdown。字段：fact_checks（数组）、risk_findings（数组）。"
        "每项包含 claim, verdict(supported|contradicted|not_found|not_applicable), reason, contract_quote, "
        "evidence_ids(只能使用给定 chunk_id), risk_level(high|medium|low), suggestion。"
    )
    user_prompt = json.dumps(
        {"contract_text": (contract_text or "")[:12000], "structured_fields": structured_fields or {}, "evidence": source_payload, "deterministic_findings": findings or []},
        ensure_ascii=False,
    )
    try:
        client = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL, timeout=settings.AI_TIMEOUT_SECONDS)
        response = client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1,
            stream=False,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        payload = _parse_json(raw)
        fact_checks = [_normalise_item(item, evidence_map, contract_text=contract_text) for item in payload["fact_checks"]]
        risks = [_normalise_item(item, evidence_map, risk=True, contract_text=contract_text) for item in payload["risk_findings"]]
        fact_checks = [item for item in fact_checks if item is not None]
        risks = [item for item in risks if item is not None]
        fact_checks = _dedupe_items(fact_checks)
        risks = _dedupe_items(risks)
        _merge_findings(fact_checks, findings, evidence_map, contract_text=contract_text)
        fact_keys = {_finding_key(item) for item in fact_checks}
        fact_claims = {_claim_key(item) for item in fact_checks}
        risks = [item for item in risks if _finding_key(item) not in fact_keys and _claim_key(item) not in fact_claims]
        return {"fact_checks": fact_checks, "risk_findings": risks, "coverage": _coverage(fact_checks, risks), "engine": "deepseek", "fallback_reason": None}
    except ValueError as exc:
        if str(exc) == "invalid_response":
            logger.warning("DeepSeek contract review returned invalid JSON")
            return _fallback(contract_text, evidence, findings, "invalid_response")
        logger.warning("DeepSeek contract review failed (%s)", type(exc).__name__)
        return _fallback(contract_text, evidence, findings, "provider_error")
    except Exception as exc:  # noqa: BLE001
        logger.warning("DeepSeek contract review failed (%s)", type(exc).__name__)
        return _fallback(contract_text, evidence, findings, "provider_error")
