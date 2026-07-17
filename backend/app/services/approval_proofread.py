"""AI 合同校对服务（审批单附件 ⇄ 合同管理原件 · 文本比对）。

链路：审批单的「合同编号 + 合同附件」 vs 合同管理模块按编号取到的「合同记录 + 原始附件」，
分别提取文本后交 DeepSeek 分析差异，并做编号一致性核对。
降级：无 DEEPSEEK_API_KEY / 调用失败 → 规则引擎兜底成文（接口永不 500）。
"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger("app.approval_proofread")

_MAX_CHARS = 9000  # 每份文本喂给模型的上限（控 token）

SYSTEM_PROMPT = (
    "你是集团合同稽核助手。任务：核对【审批单所附合同附件】与【合同管理系统登记的"
    "合同原件】的【正文内容】是否存在实质性差异。\n"
    "【分析边界——仅限正文】只比对合同正文：条款、双方义务与责任、金额与价款、"
    "标的/服务内容、履行期限、付款方式、定义条款、违约与赔偿等正文实质内容。\n"
    "【必须排除——不得作为差异依据】完全忽略、跳过以下非正文内容，不得据此判定差异："
    "①合同末尾的落款信息（落款单位/人名、落款处甲乙方署名）；②签署日期栏、日期落款；"
    "③盖章区域、公章/合同专用章的有无与位置；④电子签章、手写签名及其图片；"
    "⑤整个签字页/签署页/尾部签署区。\n"
    "【抗干扰规则】若两份文本仅在落款、盖章、签章、日期栏、签字页不同（如一方有章"
    "另一方无、落款人名不同、签署日期不同），一律视为正常，不得列为差异、不得在结论"
    "或差异明细中提及；仅当正文实质条款不同才判定“存在差异”。正文一致而仅落款/盖章/"
    "签署不同时，结论必须为“一致”。\n"
    "【严禁】不做通用总结、不复述全文、不臆造文本中不存在的内容；仅依据给定文本比对。\n"
    "【输出格式】Markdown，简洁：\n"
    "## 校对结论\n一句话给出【一致】或【存在差异】（仅依据正文；落款/盖章/签署差异不影响结论）。\n"
    "## 差异明细\n正文一致则写“正文未发现实质性差异”；否则逐条列出：正文字段/条款 → "
    "审批单附件内容 → 合同原件内容。（不得列出落款/盖章/签章/日期栏/签字页相关内容）\n"
    "## 风险提示\n针对正文差异给出稽核建议（无差异写“无”）。"
)


def _contains_no(text: str, contract_no: str) -> bool:
    if not (text and contract_no):
        return False
    norm = contract_no.strip().replace(" ", "")
    return bool(norm) and norm in text.replace(" ", "")


def proofread(
    contract_no: str,
    form_text: str,
    contract_found: bool,
    contract_no_matched: str,
    contract_text: str,
) -> dict:
    """返回 {markdown, engine, contract_found, no_consistent, has_form_text, has_contract_text}。"""
    form_text = (form_text or "").strip()
    contract_text = (contract_text or "").strip()
    no_consistent = bool(contract_found and contract_no and contract_no_matched
                         and contract_no.strip() == contract_no_matched.strip())

    meta = {
        "contract_found": contract_found,
        "no_consistent": no_consistent,
        "has_form_text": bool(form_text),
        "has_contract_text": bool(contract_text),
    }

    # 合同库无此编号：无需比对内容，直接告警（不调用模型）
    if not contract_found:
        md = (
            "## 校对结论\n**存在差异** —— 合同管理系统中未找到编号为 "
            f"`{contract_no or '（空）'}` 的合同记录。\n\n"
            "## 差异明细\n- 合同编号：审批单填写 `%s` → 合同库**无对应记录**\n\n"
            "## 风险提示\n- 请核实审批单填写的合同编号是否正确，或该合同是否已在「合同管理」中登记。"
            % (contract_no or "（空）")
        )
        return {"markdown": md, "engine": "rule", **meta}

    if settings.AI_ENABLED and form_text and contract_text:
        try:
            md = _proofread_by_llm(contract_no, form_text, contract_text)
            return {"markdown": md, "engine": "deepseek", **meta}
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek 合同校对失败，回退规则引擎：%s", exc)

    return {"markdown": _proofread_by_rules(contract_no, form_text, contract_text, meta), "engine": "rule", **meta}


def _proofread_by_llm(contract_no: str, form_text: str, contract_text: str) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        timeout=settings.AI_TIMEOUT_SECONDS,
    )
    a = form_text[:_MAX_CHARS]
    b = contract_text[:_MAX_CHARS]
    user_prompt = (
        f"【审批单填写的合同编号】{contract_no or '（空）'}\n\n"
        f"【审批单所附合同附件·提取文本】\n{a or '（未提取到文本）'}\n\n"
        f"【合同管理系统登记的合同原件·提取文本】\n{b or '（未提取到文本）'}"
    )
    resp = client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        stream=False,
    )
    md = (resp.choices[0].message.content or "").strip()
    if not md:
        raise ValueError("模型返回空内容")
    return md


def _proofread_by_rules(contract_no: str, form_text: str, contract_text: str, meta: dict) -> str:
    """无大模型 / 缺附件文本时的兜底：做编号出现性核对 + 人工复核清单。"""
    no_in_form = _contains_no(form_text, contract_no)
    no_in_contract = _contains_no(contract_text, contract_no)
    lines = [
        "> ⚠️ 未接入大模型或缺少可提取文本（无附件 / 扫描件 / 旧 .doc），以下为规则化核对结果，供人工复核。\n",
        "## 校对结论",
    ]
    if not meta["has_form_text"] or not meta["has_contract_text"]:
        miss = []
        if not meta["has_form_text"]:
            miss.append("审批单附件")
        if not meta["has_contract_text"]:
            miss.append("合同原件")
        lines.append(f"**无法自动比对内容** —— 未能从【{'、'.join(miss)}】提取到文本。")
    else:
        lines.append("**需人工确认** —— 已提取双方文本，但未接入大模型，无法自动判定实质差异。")
    lines += [
        "\n## 差异明细",
        f"- 合同编号一致性：审批单填 `{contract_no or '（空）'}`，合同库{'已' if meta['contract_found'] else '未'}登记该编号。",
        f"- 编号是否出现在审批单附件文本：{'是' if no_in_form else '否/未知'}。",
        f"- 编号是否出现在合同原件文本：{'是' if no_in_contract else '否/未知'}。",
        "\n## 风险提示",
        "- 建议人工逐项核对甲乙方、金额、标的、期限与付款方式；如需自动判定，请配置 DEEPSEEK_API_KEY。",
    ]
    return "\n".join(lines)
