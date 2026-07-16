"""DeepSeek 合同 AI 审查服务。

链路：合同文本(附件提取/字段兜底) + 法规知识库文本 → DeepSeek → Markdown 审查意见。
降级：无 DEEPSEEK_API_KEY / 调用失败 → 规则引擎兜底成文（接口永不 500）。
视角：System Prompt 锚定「我方（本公司）利益立场」，只列对我方不利/风险/权利义务
     不对等的条款并给修改建议，禁止通用总结与客套；低温度、只依据给定文本、不臆造法条。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.knowledge import KnowledgeDoc

logger = logging.getLogger("app.contract_review")

_MAX_CONTRACT_CHARS = 12000   # 合同正文喂给模型的上限（控 token）
_MAX_KB_CHARS = 8000          # 法规知识库聚合上限

SYSTEM_PROMPT = (
    "你是集团法务合规专家，代表【我方（山东出版供应链管理公司，即合同中的本方/委托审查方）】"
    "审查合同。你唯一的立场是：最大化保护我方利益、识别并控制我方风险。\n\n"
    "【审查任务】仅聚焦对我方不利的内容，逐条排查并输出：\n"
    "1. 对我方不利、加重我方义务或免除/减轻对方责任的条款；\n"
    "2. 潜在法律风险（违约责任不对等、付款/交付/验收、争议解决与管辖、保密与知识产权、"
    "解除与终止、赔偿上限与责任范围等）；\n"
    "3. 权利义务不对等、显失公平的条款。\n"
    "每一条必须包含三要素：①条款定位（引用合同原文或条款号）→ ②对我方的不利点/风险 → "
    "③可直接落地的修改建议。优先对照随附【法规知识库】，相关处标注所参照的制度/法规名称。\n\n"
    "【严禁】不做通用性合同总结、不复述合同内容；不输出寒暄、客套、免责声明或与风险无关的赞美；"
    "对我方有利/中性的条款不必列出（除非用于对比说明不对等）；不臆造合同中不存在的条款或法条，"
    "合同未覆盖之处写“合同未明确”。\n\n"
    "【输出格式】Markdown，不要任何多余前后缀：\n"
    "## 一、对我方不利/风险条款（逐条）\n"
    "对每条按如下结构输出：\n"
    "- **条款定位**：引用原文/条款号\n"
    "- **不利点/风险**：……\n"
    "- **修改建议**：……\n"
    "（若确未发现明显对我方不利的条款，直接写“未发现明显对我方不利的条款”，不得编造。）\n"
    "## 二、总体风险等级与优先修改清单\n"
    "给出风险等级（低 / 中 / 高）与按优先级排序的必改项清单。"
)


def aggregate_kb_text(db: Session) -> tuple[str, list[str]]:
    """聚合法规知识库全文（截断），返回 (文本, 使用到的文件标题列表)。"""
    docs = db.scalars(select(KnowledgeDoc).order_by(KnowledgeDoc.id.asc())).all()
    if not docs:
        return "", []
    parts: list[str] = []
    titles: list[str] = []
    total = 0
    for d in docs:
        seg = (d.content or "").strip()
        if not seg:
            continue
        remain = _MAX_KB_CHARS - total
        if remain <= 0:
            break
        seg = seg[:remain]
        parts.append(f"【{d.category}·{d.title}】\n{seg}")
        titles.append(d.title)
        total += len(seg)
    return "\n\n".join(parts), titles


def review(contract_text: str, kb_text: str) -> dict:
    """返回 {markdown, engine}。engine=deepseek/rule。"""
    contract_text = (contract_text or "").strip()
    if settings.AI_ENABLED:
        try:
            md = _review_by_llm(contract_text, kb_text)
            return {"markdown": md, "engine": "deepseek"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek 合同审查失败，回退规则引擎：%s", exc)
    return {"markdown": _review_by_rules(contract_text, kb_text), "engine": "rule"}


def _review_by_llm(contract_text: str, kb_text: str) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        timeout=settings.AI_TIMEOUT_SECONDS,
    )
    body = contract_text[:_MAX_CONTRACT_CHARS]
    if len(contract_text) > _MAX_CONTRACT_CHARS:
        body += "\n……（合同过长已截断）"
    kb = kb_text.strip() or "（未配置法规知识库，请基于通行法律规范审查）"
    user_prompt = (
        f"【法规知识库（分析依据）】\n{kb}\n\n"
        f"【合同文本（待审查）】\n{body or '（未提取到合同文本）'}"
    )
    resp = client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        stream=False,
    )
    md = (resp.choices[0].message.content or "").strip()
    if not md:
        raise ValueError("模型返回空内容")
    return md


def _review_by_rules(contract_text: str, kb_text: str) -> str:
    """无大模型时的兜底：结构化清单，提示人工复核。"""
    has_text = bool(contract_text)
    kb_note = "已加载法规知识库作为参考。" if kb_text else "未配置法规知识库，建议先在「法规知识库」中上传公司合同法/集团制度/法律规范。"
    body_note = "已提取到合同文本。" if has_text else "未提取到合同文本（可能无附件或为扫描件/旧 .doc 格式）。"
    return (
        "> ⚠️ 未接入大模型（未配置 DEEPSEEK_API_KEY 或调用失败），以下为【站在我方立场】的规则化风险核查清单，供人工复核。\n\n"
        "## 一、对我方不利/风险条款（需人工逐条核对）\n"
        f"- 是否存在单方面加重我方义务、免除或减轻对方责任的条款。（{body_note}）\n"
        "- 违约责任是否对等（我方违约赔偿是否显著重于对方）。\n"
        "- 付款 / 交付 / 验收条件是否对我方不利、是否先付款后交付。\n"
        "- 争议解决与管辖地是否约定在对我方不利的地点。\n"
        "- 保密、知识产权归属、赔偿上限与责任范围是否损害我方权益。\n"
        f"- 是否符合集团用印/审批权限与制度要求。（{kb_note}）\n"
        "## 二、总体风险等级与优先修改清单\n"
        "- 风险等级：待人工评估；建议就上述对我方不利之处逐条提出修改后再签署。"
    )
