"""DeepSeek 合同 AI 审查服务。

链路：合同文本(附件提取/字段兜底) + 法规知识库文本 → DeepSeek → Markdown 审查意见。
降级：无 DEEPSEEK_API_KEY / 调用失败 → 规则引擎兜底成文（接口永不 500）。
准确性：低温度、System Prompt 严格锚定「公司合同法/集团企业制度/法律规范」，
       只依据给定文本、指出条款位置、不臆造法条，输出固定四段 Markdown。
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
    "你是集团法务合规专家。请依据《合同法》、集团企业管理制度及通行法律规范，"
    "对用户提供的【合同文本】进行专业审查，并优先参考用户随附的【法规知识库】内容。\n"
    "严格按以下 Markdown 结构输出，不要输出多余前后缀：\n"
    "## 一、权利与义务对等性\n"
    "分析双方权利义务是否对等、有无显失公平条款（引用合同中对应表述）。\n"
    "## 二、明显法律风险\n"
    "逐条列出识别到的法律风险，每条注明依据的合同条款/表述与风险点。\n"
    "## 三、集团合规符合性\n"
    "对照集团企业制度与法规知识库，指出合规/不合规之处。\n"
    "## 四、总体结论与修改建议\n"
    "给出总体风险等级（低 / 中 / 高）与可执行的修改建议清单。\n\n"
    "要求：只依据给定文本判断，不臆造不存在的条款或法条；合同文本未覆盖之处，"
    "明确写“合同未明确”；若提供了法规知识库，请在相关结论后标注所参照的制度/法规名称。"
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
        "> ⚠️ 未接入大模型（未配置 DEEPSEEK_API_KEY 或调用失败），以下为规则化审查清单，供人工复核。\n\n"
        "## 一、权利与义务对等性\n"
        f"- 请人工核对双方权利义务是否对等、有无单方面加重乙方义务或免除甲方责任的条款。（{body_note}）\n"
        "## 二、明显法律风险\n"
        "- 重点核查：违约责任是否对等、争议解决与管辖、付款与交付条件、保密与知识产权、解除与终止条款。\n"
        "## 三、集团合规符合性\n"
        f"- 对照集团企业制度与用印/审批权限要求核验。（{kb_note}）\n"
        "## 四、总体结论与修改建议\n"
        "- 风险等级：待人工评估。建议补齐上述要素后再签署。"
    )
