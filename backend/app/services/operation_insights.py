"""Aggregate-only explanations with deterministic offline fallback."""
import json
from collections import Counter
from decimal import Decimal

from app.core.config import settings
from app.services.deepseek_chat import deepseek_client_options


def sanitize_aggregate_result(result):
    """Allowlist numeric aggregates and controlled categories; never forward identifiers/text."""
    totals = {}
    for metric in ("settlement_amount", "writeoff_amount", "order_count"):
        lines = [line for line in getattr(result, "lines", []) if line.metric == metric]
        summary = getattr(result, "summary", None)
        totals[metric] = str(getattr(summary, metric)) if summary is not None else str(sum((line.forecast for line in lines if line.forecast is not None), Decimal(0)))
    return {
        "totals": totals,
        "confidence": dict(Counter(line.confidence for line in getattr(result, "lines", []))),
        "quality_issue_count": len(getattr(result, "quality_issues", [])),
        "anomaly_count": len(getattr(result, "anomalies", [])),
        "insufficient_line_count": sum(line.forecast is None for line in getattr(result, "lines", [])),
        "factor_adjustment": str(sum((line.factor_adjustment for line in getattr(result, "lines", []) if line.metric == "settlement_amount"), Decimal(0))),
    }


def render_operation_insights(result):
    aggregate = sanitize_aggregate_result(result)
    fallback = {
        "engine": "rules",
        "summary": f"基于已确认台账汇总（预测仅统计可计算分层，数据不足分层 {aggregate['insufficient_line_count']} 个）：结算金额 {aggregate['totals']['settlement_amount']} 元，核销金额 {aggregate['totals']['writeoff_amount']} 元，订单数 {aggregate['totals']['order_count']}。",
        "recommendations": ["预测仅供经营参考，请结合置信度安排资源。", "数据不足或存在质量问题时，先补齐并确认台账；影响因素请人工维护或导入。"],
    }
    if not settings.AI_ENABLED or not settings.DEEPSEEK_API_KEY:
        return fallback
    try:
        from openai import OpenAI
        client = OpenAI(**deepseek_client_options())
        response = client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "仅依据聚合数据解释预测，不编造原因。输出JSON：summary字符串，recommendations非空字符串数组。"},
                {"role": "user", "content": json.dumps(aggregate, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"}, temperature=0.2,
        )
        data = json.loads(response.choices[0].message.content)
        if not isinstance(data.get("summary"), str) or not data["summary"].strip():
            return fallback
        recommendations = data.get("recommendations")
        if not isinstance(recommendations, list) or not recommendations or not all(isinstance(item, str) and item.strip() for item in recommendations):
            return fallback
        return {"engine": "deepseek", "summary": data["summary"], "recommendations": recommendations}
    except Exception:
        return fallback
