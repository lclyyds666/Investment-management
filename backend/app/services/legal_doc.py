"""生成「法律文件审批表」.docx(严格 3cm 行高 + 方正小标宋简体/仿宋_GB2312)。

参考模板:`供管法律文件审批表.doc`。用 python-docx(已装,无新依赖)精确控制
行高与字体,用户用 Word 打开打印,字体在本机呈现(出版单位通常已装公文字体)。
"""
from __future__ import annotations

import io

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

TITLE_TEXT = "山东出版供应链法律文件审批表"
PUBLISHER = "出版供应链"          # 发文单位默认值
TITLE_FONT = "方正小标宋简体"      # 标题字体(公文标准)
BODY_FONT = "仿宋_GB2312"          # 正文字体(公文标准)
ROW_HEIGHT_CM = 3                  # 严格行高 3cm

# 4 个意见栏(角色值 → 栏目名),顺序即审批流转顺序
OPINION_ROLES = [
    ("scm_director", "供管公司负责人意见"),
    ("legal_counsel", "法律顾问意见"),
    ("risk_auditor", "投资公司法务风控部意见"),
    ("invest_director", "投资公司分管领导意见"),
]


def _set_font(run, name: str, size_pt: float, bold: bool = False) -> None:
    """设置 run 字体(含中文 eastAsia,确保 Word 用指定中文字体渲染)。"""
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:eastAsia"), name)


def _fill_cell(cell, text: str, *, font: str = BODY_FONT, size: float = 14,
               bold: bool = False, center: bool = False) -> None:
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    lines = str(text or "").split("\n")
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    for r in list(p.runs):
        r.text = ""
    run = p.add_run(lines[0])
    _set_font(run, font, size, bold)
    for extra in lines[1:]:
        np = cell.add_paragraph()
        np.alignment = p.alignment
        _set_font(np.add_run(extra), font, size, bold)


def build_legal_doc(contract: dict, opinions: dict) -> bytes:
    """生成审批表 .docx 字节。

    contract: {title, contract_no, sign_date, creator_name}
    opinions: {role_value: {comment, approver_name, date}}
    """
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Cm(2)
    sec.left_margin = sec.right_margin = Cm(2.5)

    # 标题
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(h.add_run(TITLE_TEXT), TITLE_FONT, 22, bold=True)
    doc.add_paragraph()  # 标题与表格间距

    table = doc.add_table(rows=0, cols=6)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    def add_row():
        row = table.add_row()
        row.height = Cm(ROW_HEIGHT_CM)
        row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
        return row

    # 第一行:发文单位 / 发文时间 / 发文人员
    c = add_row().cells
    _fill_cell(c[0], "发文单位", bold=True, center=True)
    _fill_cell(c[1], PUBLISHER, center=True)
    _fill_cell(c[2], "发文时间", bold=True, center=True)
    _fill_cell(c[3], contract.get("sign_date") or "", center=True)
    _fill_cell(c[4], "发文人员", bold=True, center=True)
    _fill_cell(c[5], contract.get("creator_name") or "", center=True)

    # 文件名称
    r = add_row()
    _fill_cell(r.cells[0], "文件名称", bold=True, center=True)
    _fill_cell(r.cells[1].merge(r.cells[5]), contract.get("title") or "")

    # 合同编号
    r = add_row()
    _fill_cell(r.cells[0], "合同编号", bold=True, center=True)
    _fill_cell(r.cells[1].merge(r.cells[5]), contract.get("contract_no") or "")

    # 4 个意见栏
    for role, label in OPINION_ROLES:
        r = add_row()
        _fill_cell(r.cells[0], label, bold=True, center=True)
        op = opinions.get(role)
        if op:
            body = op.get("comment") or "同意"
            sign = "　".join(x for x in [op.get("approver_name"), op.get("date")] if x)
            text = f"{body}\n\n{sign}" if sign else body
        else:
            text = ""
        _fill_cell(r.cells[1].merge(r.cells[5]), text)

    # 标签列固定宽
    for row in table.rows:
        row.cells[0].width = Cm(3.2)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
