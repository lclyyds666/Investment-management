"""AI 智能体服务：经营/财务风险诊断与闲置资金投资建议。

设计要点（商用级）：
- 以真实聚合数据（营收/成本/利润/订单/待开票/审批积压）为 Context 喂给大模型（DeepSeek）。
- DeepSeek 走 OpenAI 兼容协议；未配置 API Key 时自动回退到内置规则引擎，保证功能永不失效。
- 强制模型输出 JSON，解析为前端约定结构 {summary, metrics, risks, suggestions}。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger("app.ai_agent")


def _yuan(v: float) -> str:
    return f"¥{float(v):,.0f}"


def diagnose(metrics: dict[str, Any]) -> dict[str, Any]:
    """入口：优先调用 DeepSeek，失败或未配置则回退规则引擎。

    :param metrics: 已由端点从数据库聚合好的真实经营/财务指标。
    :return: {summary, metrics, risks, suggestions, engine}
    """
    if settings.AI_ENABLED:
        try:
            result = _diagnose_by_llm(metrics)
            result["engine"] = "deepseek"
            return result
        except Exception as exc:  # noqa: BLE001  任何异常都不应让接口 500
            logger.warning("DeepSeek 诊断失败，回退规则引擎：%s", exc)

    result = _diagnose_by_rules(metrics)
    result["engine"] = "rule"
    return result


# --------------------------------------------------------------------------- #
# 真实大模型：DeepSeek
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = (
    "你是山东出版供应链管理有限公司的首席财务风控 AI 顾问。"
    "你将收到公司当前真实的经营与财务聚合数据，请基于这些数据做专业、务实、可执行的诊断，"
    "输出业务风险预警与闲置资金管理/投资建议。要求：\n"
    "1. 只依据给定数据推断，不臆造具体不存在的数字；\n"
    "2. 语气专业、结论明确，金额用人民币元；\n"
    "3. 严格输出 JSON，不要输出任何多余文字或 Markdown。"
)

_JSON_SPEC = (
    "请仅输出如下 JSON 结构：\n"
    "{\n"
    '  "summary": "一段总体经营与资金状况综述（80-160字）",\n'
    '  "risks": [\n'
    '    {"level": "高|中|低", "title": "风险标题", "detail": "风险说明与应对建议"}\n'
    "  ],\n"
    '  "suggestions": [\n'
    '    {"title": "资金管理/投资建议标题", "detail": "具体建议与预期收益/流动性说明"}\n'
    "  ]\n"
    "}\n"
    "risks 给 2-4 条，suggestions 给 2-3 条。"
)


def _build_user_prompt(m: dict[str, Any]) -> str:
    return (
        "以下为本年度公司真实经营与财务数据：\n"
        f"- 总营收：{_yuan(m['revenue'])}\n"
        f"- 总成本：{_yuan(m['cost'])}\n"
        f"- 总利润：{_yuan(m['profit'])}\n"
        f"- 综合利润率：{m['margin']:.1f}%\n"
        f"- 订单总数：{m['orders']:,} 笔\n"
        f"- 估算可动用闲置资金：{_yuan(m['idle_funds'])}\n"
        f"- 待开票（应收占用）金额：{_yuan(m['pending_invoice'])}\n"
        f"- 处于 7 级审批流转中的合同：{m['pending_contracts']} 份\n\n"
        + _JSON_SPEC
    )


def _diagnose_by_llm(metrics: dict[str, Any]) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        timeout=settings.AI_TIMEOUT_SECONDS,
    )
    resp = client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(metrics)},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
        stream=False,
    )
    content = resp.choices[0].message.content or "{}"
    data = json.loads(content)

    # 归一化 + 兜底，避免模型偶发缺字段导致前端崩溃
    risks = [
        {
            "level": str(r.get("level", "中"))[:1] if str(r.get("level", "")).strip() in ("高", "中", "低") else "中",
            "title": str(r.get("title", "")).strip() or "风险提示",
            "detail": str(r.get("detail", "")).strip(),
        }
        for r in (data.get("risks") or [])
        if isinstance(r, dict)
    ]
    suggestions = [
        {
            "title": str(s.get("title", "")).strip() or "资金建议",
            "detail": str(s.get("detail", "")).strip(),
        }
        for s in (data.get("suggestions") or [])
        if isinstance(s, dict)
    ]
    summary = str(data.get("summary", "")).strip()

    # 模型偶发空返回时，用规则引擎补齐，保证有内容可展示
    if not summary or not risks or not suggestions:
        fb = _diagnose_by_rules(metrics)
        summary = summary or fb["summary"]
        risks = risks or fb["risks"]
        suggestions = suggestions or fb["suggestions"]

    return {"summary": summary, "metrics": metrics, "risks": risks, "suggestions": suggestions}


# --------------------------------------------------------------------------- #
# 回退：内置规则引擎（原逻辑，保证离线/无 Key 时仍可用）
# --------------------------------------------------------------------------- #
def _diagnose_by_rules(m: dict[str, Any]) -> dict[str, Any]:
    revenue = float(m["revenue"])
    profit = float(m["profit"])
    orders = int(m["orders"])
    margin = float(m["margin"])
    pending_invoice = float(m["pending_invoice"])
    pending_contracts = int(m["pending_contracts"])
    idle = float(m["idle_funds"])

    risks = []
    if margin < 30:
        risks.append({"level": "高", "title": "综合利润率偏低",
                      "detail": f"当前综合利润率约 {margin:.1f}%，低于健康线 30%，建议优化成本结构、聚焦高毛利业务线。"})
    else:
        risks.append({"level": "低", "title": "盈利能力稳健",
                      "detail": f"综合利润率约 {margin:.1f}%，处于健康区间，可适度扩张规模。"})
    if pending_invoice > 0:
        risks.append({"level": "中", "title": "应收/待开票资金占用",
                      "detail": f"待开票金额约 {_yuan(pending_invoice)}，存在资金回笼与税务确认风险，建议加快开票与回款节奏。"})
    if pending_contracts > 0:
        risks.append({"level": "中", "title": "合同审批积压",
                      "detail": f"有 {pending_contracts} 份合同处于 7 级审批流转中，建议关注审批时效，避免业务延误。"})

    suggestions = [
        {"title": "结构性存款配置",
         "detail": f"建议将约 {_yuan(round(idle * 0.5))} 配置为银行结构性存款，兼顾流动性与收益（预期年化 2.8%–3.2%）。"},
        {"title": "国债逆回购",
         "detail": f"月末/季末可将约 {_yuan(round(idle * 0.2))} 用于国债逆回购，捕捉短期利率高点，资金 T+1 可用。"},
        {"title": "供应链金融投放",
         "detail": f"依托核心供应商网络，将约 {_yuan(round(idle * 0.3))} 投入供应链票据/保理，提升资金周转与产业协同。"},
    ]
    summary = (
        f"本年度营收 {_yuan(revenue)}、利润 {_yuan(profit)}（利润率 {margin:.1f}%），"
        f"订单 {orders:,} 笔；结合应收与审批情况，估算当前可动用闲置资金约 {_yuan(idle)}。"
    )
    return {"summary": summary, "metrics": m, "risks": risks, "suggestions": suggestions}
