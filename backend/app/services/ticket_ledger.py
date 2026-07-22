"""文旅业务·门票平台核销台账计算服务（泉州欧乐堡专属逻辑）。

职责：
1. 解析平台对账明细 xlsx（多个「周」明细 Sheet），逐单累加
   订单实收 − 软件服务费 − 达人服务费 − 团长服务费 − 服务商服务费
   得到「服务商到账金额」，并解析对账周期跨度 / 核对日期文本。
2. 出版应得到账金额 B = 服务商到账 − 服务商佣金(手工录入)；再按固定拆分比例计算：
     景区核销金额 = B × 核销率(默认 90%)
     服务费       = B × 服务费率(默认 4%)
     结算金额     = 景区核销金额 + 服务费   (= B × 94%)
   另按期次递推出景区待核销金额(滚动余额，见 running_pending)。
3. 用 openpyxl 生成标准格式业务台账 xlsx（含合计行）供导出。

列一律按「表头名」定位，兼容明细表 70/72 列的差异；金额解析宽松（去 ¥、逗号等）。
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO

import openpyxl

# 台账固定字段（泉州欧乐堡门票平台）
DEFAULT_TICKET_PRODUCT = "水上世界/童话世界/海洋王国"
DEFAULT_RATE_HEXIAO = Decimal("0.90")  # 景区核销率
DEFAULT_RATE_FEE = Decimal("0.04")     # 实收服务费率
_CENT = Decimal("0.01")

# 明细表关键列的表头名（按名定位，抗列数差异）
COL_SHISHOU = "订单实收金额"
COL_RUANJIAN = "软件服务费"
COL_DAREN = "达人服务费"
COL_TUANZHANG = "团长服务费"
COL_HEXIAO_TIME = "核销时间"
# 服务商到账金额 = 订单实收 − 软件 − 达人 − 团长（明细中费用列为负数，直接相加）。
# 注意：明细里的「服务商服务费」列其实是 -(服务商到账金额)，若一并相加会把结果抵消为 0，故不纳入。
_FEE_COLS = (COL_RUANJIAN, COL_DAREN, COL_TUANZHANG)


def _num(v):
    """宽松转 Decimal（去 ¥、逗号、%、空格等）；无法解析返回 None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return Decimal(str(v))
        except InvalidOperation:
            return None
    s = re.sub(r"[^\d.\-]", "", str(v).strip())
    if not s or s in ("-", ".", "-."):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _q(v: Decimal) -> Decimal:
    """金额统一四舍五入到分。"""
    return (v or Decimal("0")).quantize(_CENT, rounding=ROUND_HALF_UP)


def _to_date(v):
    """单元格转 date；解析失败返回 None。"""
    if v is None or str(v).strip() == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _header_index(header: list, name: str) -> int:
    """在表头行里按名找列索引；找不到返回 -1。"""
    for i, h in enumerate(header):
        if h is not None and str(h).strip() == name:
            return i
    return -1


def _is_detail_sheet(ws_title: str) -> bool:
    """判断是否为「周明细」Sheet（含核销明细，非对账单汇总页）。"""
    t = ws_title or ""
    return "明细" in t


def _period_from_filename(filename: str) -> tuple[date | None, date | None]:
    """从文件名解析对账周期，如 对账明细-2026.04.29-2026.05.19.xlsx。"""
    if not filename:
        return None, None
    m = re.search(
        r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\D+(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})",
        filename,
    )
    if not m:
        return None, None
    try:
        d1 = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        d2 = date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
        return d1, d2
    except ValueError:
        return None, None


def parse_reconciliation(content: bytes, filename: str = "") -> dict:
    """解析一个对账明细 xlsx，返回汇总。

    返回:
      {
        "supplier_received": Decimal,   # 服务商到账金额 = Σ(订单实收 - 软件 - 达人 - 团长)
        "order_count": int,             # 有效核销订单数
        "period_start": date|None,
        "period_end": date|None,
        "period_text": str,             # 对账周期文本，如 2026/4/29-2026/5/19
        "check_date_text": str,         # 核对日期（同 period_text，供台账「核对日期」列）
        "sheets": [sheet 名列表],
      }

    对账周期优先取自文件名（如 对账明细-2026.04.29-2026.05.19.xlsx）；
    文件名无法解析时，回退到核销时间跨度。
    """
    # read_only=True 流式读取，内存可控；用 try/finally 保证异常时也释放工作簿
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True, read_only=True)

    supplier_received = Decimal("0")
    order_count = 0
    min_dt: date | None = None
    max_dt: date | None = None
    used_sheets: list[str] = []

    try:
        for ws in wb.worksheets:
            if not _is_detail_sheet(ws.title):
                continue  # 跳过对账单汇总页/其它页

            rows_iter = ws.iter_rows(values_only=True)
            header = None
            for raw in rows_iter:
                if raw and any(c is not None and str(c).strip() for c in raw):
                    header = list(raw)
                    break
            if header is None:
                continue

            i_shishou = _header_index(header, COL_SHISHOU)
            if i_shishou < 0:
                continue  # 非核销明细表结构，跳过
            i_fees = [_header_index(header, c) for c in _FEE_COLS]
            i_time = _header_index(header, COL_HEXIAO_TIME)

            used_sheets.append(ws.title)
            for raw in rows_iter:
                if not raw:
                    continue
                shishou = _num(raw[i_shishou]) if i_shishou < len(raw) else None
                fee_vals = [
                    (_num(raw[idx]) if 0 <= idx < len(raw) else None) for idx in i_fees
                ]
                # 空行 / 小计行：实收与全部费用都无值 → 跳过
                if shishou is None and all(f is None for f in fee_vals):
                    continue
                base = (shishou or Decimal("0"))
                for f in fee_vals:
                    base += (f or Decimal("0"))  # 费用在明细中为负数，直接相加
                supplier_received += base
                order_count += 1

                if 0 <= i_time < len(raw):
                    d = _to_date(raw[i_time])
                    if d:
                        min_dt = d if (min_dt is None or d < min_dt) else min_dt
                        max_dt = d if (max_dt is None or d > max_dt) else max_dt
    finally:
        wb.close()

    # 周期优先取文件名；否则回退核销时间跨度
    fn_start, fn_end = _period_from_filename(filename)
    p_start = fn_start or min_dt
    p_end = fn_end or max_dt

    period_text = ""
    if p_start and p_end:
        period_text = f"{p_start.year}/{p_start.month}/{p_start.day}-{p_end.year}/{p_end.month}/{p_end.day}"

    return {
        "supplier_received": _q(supplier_received),
        "order_count": order_count,
        "period_start": p_start,
        "period_end": p_end,
        "period_text": period_text,
        "check_date_text": period_text,
        "sheets": used_sheets,
    }


def compute_row(
    supplier_received: Decimal,
    supplier_commission: Decimal = Decimal("0"),
    rate_hexiao: Decimal = DEFAULT_RATE_HEXIAO,
    rate_fee: Decimal = DEFAULT_RATE_FEE,
) -> dict:
    """由服务商到账、服务商佣金与比例计算台账计算列。

      出版应得到账金额 B = 服务商到账 - 服务商佣金
      景区核销金额 = B × 核销率
      服务费       = B × 服务费率
      结算金额     = 景区核销金额 + 服务费
    """
    received = supplier_received or Decimal("0")
    commission = supplier_commission or Decimal("0")
    b = received - commission
    hexiao = _q(b * rate_hexiao)
    fee = _q(b * rate_fee)
    jinying = _q(hexiao + fee)
    return {
        "supplier_commission": _q(commission),
        "publisher_due": _q(b),        # 出版应得到账金额 = 服务商到账 - 服务商佣金
        "hexiao_amount": hexiao,       # 景区核销金额
        "service_fee": fee,            # 服务费
        "jinying_amount": jinying,     # 结算金额
    }


def running_pending(prev_balance: Decimal, payment_amount: Decimal, hexiao_amount: Decimal) -> Decimal:
    """期次递推：本期景区待核销金额 = 上期剩余余额 + 本期付款金额 - 本期景区核销金额。

    首期时 prev_balance 传 0 即为「首期付款金额 - 首期景区核销金额」。
    """
    prev = prev_balance or Decimal("0")
    pay = payment_amount or Decimal("0")
    hexiao = hexiao_amount or Decimal("0")
    return _q(prev + pay - hexiao)


# 导出台账列顺序（对齐手工业务台账样表；景区待核销金额紧邻景区核销金额右侧）
_EXPORT_HEADERS = [
    "平台", "景区门票", "核对日期",
    "景区核销金额", "景区待核销金额", "付款金额", "结算金额", "服务费",
    "回款日期", "回款金额",
]


def _fmt_date(v) -> str:
    if not v:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return str(v)


def _fmt_amount(v):
    if v is None or v == "":
        return ""
    d = _num(v)
    return float(_q(d)) if d is not None else str(v)


def build_export_workbook(rows: list[dict], title: str = "业务台账") -> bytes:
    """生成标准格式业务台账 xlsx（含标题行 + 表头 + 数据 + 合计行）。

    rows 每项字段：pay_date, platform, ticket_product, check_date_text,
    hexiao_amount, jinying_amount, service_fee, repay_date, repay_amount。
    """
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "业务台账"

    ncol = len(_EXPORT_HEADERS)
    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 标题行（合并）
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    tc = ws.cell(row=1, column=1, value=title)
    tc.font = Font(size=13, bold=True)
    tc.alignment = center

    # 表头
    head_fill = PatternFill("solid", fgColor="DCE6F1")
    for c, name in enumerate(_EXPORT_HEADERS, start=1):
        cell = ws.cell(row=2, column=c, value=name)
        cell.font = Font(bold=True)
        cell.alignment = center
        cell.fill = head_fill
        cell.border = border

    # 数据行
    sum_hexiao = Decimal("0")
    sum_pending = Decimal("0")
    sum_payment = Decimal("0")
    sum_jinying = Decimal("0")
    sum_fee = Decimal("0")
    sum_repay = Decimal("0")
    r = 3
    for row in rows:
        vals = [
            row.get("platform", "") or "",
            row.get("ticket_product", "") or DEFAULT_TICKET_PRODUCT,
            row.get("check_date_text", "") or "",
            _fmt_amount(row.get("hexiao_amount")),
            _fmt_amount(row.get("pending_writeoff")),
            _fmt_amount(row.get("payment_amount")),
            _fmt_amount(row.get("jinying_amount")),
            _fmt_amount(row.get("service_fee")),
            _fmt_date(row.get("repay_date")),
            _fmt_amount(row.get("repay_amount")),
        ]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.alignment = center
            cell.border = border
        sum_hexiao += _num(row.get("hexiao_amount")) or Decimal("0")
        sum_payment += _num(row.get("payment_amount")) or Decimal("0")
        sum_jinying += _num(row.get("jinying_amount")) or Decimal("0")
        sum_fee += _num(row.get("service_fee")) or Decimal("0")
        sum_repay += _num(row.get("repay_amount")) or Decimal("0")
        r += 1
    # 景区待核销金额为滚动余额，合计取末期余额（最后一行的值）
    if rows:
        sum_pending = _num(rows[-1].get("pending_writeoff")) or Decimal("0")

    # 合计行
    total_fill = PatternFill("solid", fgColor="FDE9D9")
    total_vals = [
        "合计", "", "",
        float(_q(sum_hexiao)), float(_q(sum_pending)), float(_q(sum_payment)),
        float(_q(sum_jinying)), float(_q(sum_fee)),
        "", float(_q(sum_repay)),
    ]
    for c, v in enumerate(total_vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font = Font(bold=True)
        cell.alignment = center
        cell.fill = total_fill
        cell.border = border

    # 列宽
    widths = [8, 22, 20, 15, 15, 14, 15, 14, 13, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
