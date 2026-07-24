"""文旅业务·门票平台核销台账计算服务（泉州欧乐堡专属逻辑）。

职责：
1. 解析平台对账明细 xlsx（多个「周」明细 Sheet），逐单累加
   订单实收 − 软件服务费 − 达人服务费 − 团长服务费 − 服务商服务费
   得到「服务商到账金额」，并解析对账周期跨度 / 核对日期文本。
2. 出版应得到账金额 B = 服务商到账 − 服务商佣金(手工录入)；再按比例计算：
     景区核销金额 = B × 核销率(默认 90%)
     结算金额     = B × 结算费率(默认 94%)
     服务费       = 结算金额 − 景区核销金额   (默认口径 = B × 4%)
   另按期次递推出景区待核销金额(滚动余额，见 running_pending)。
3. 用 openpyxl 生成标准格式业务台账 xlsx（含合计行）供导出。

列一律按「表头名」定位，兼容明细表 70/72 列的差异；金额解析宽松（去 ¥、逗号等）。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO

import openpyxl

# 台账固定字段（泉州欧乐堡门票平台）
DEFAULT_TICKET_PRODUCT = "水上世界/童话世界/海洋王国"
DEFAULT_RATE_HEXIAO = Decimal("0.90")  # 景区核销率
# 结算费率：结算金额 = 出版应得B × 结算费率。默认 0.94（= 旧核销率0.90 + 旧服务费率0.04），
# 保证历史/现有台账数值完全不变；服务费改为派生 = 结算金额 − 景区核销金额。
DEFAULT_RATE_SETTLE = Decimal("0.94")
DEFAULT_RATE_FEE = Decimal("0.04")     # 旧服务费率（保留常量，仅历史/迁移回填参考）
# 服务商佣金默认率(对订单实收金额)：服务商佣金 = 订单实收×6% − 达人服务费 − 团长服务费
DEFAULT_COMMISSION_RATE = Decimal("0.06")
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
    positive_count = 0   # 订单实收金额为正数的订单数（核销率分子）
    min_dt: date | None = None
    max_dt: date | None = None
    used_sheets: list[str] = []
    # 按日期分组：核销时间 → 当日 {received, shishou, daren, tuanzhang}
    daily: dict[str, dict] = {}

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
                if shishou is not None and shishou > 0:
                    positive_count += 1

                d = _to_date(raw[i_time]) if 0 <= i_time < len(raw) else None
                if d:
                    min_dt = d if (min_dt is None or d < min_dt) else min_dt
                    max_dt = d if (max_dt is None or d > max_dt) else max_dt
                # 按日归集（fee_vals 顺序 = 软件/达人/团长）
                key = d.isoformat() if d else "NA"
                dd = daily.setdefault(key, {
                    "received": Decimal("0"), "shishou": Decimal("0"),
                    "daren": Decimal("0"), "tuanzhang": Decimal("0"),
                })
                dd["received"] += base
                dd["shishou"] += (shishou or Decimal("0"))
                dd["daren"] += (fee_vals[1] or Decimal("0"))       # 达人(负)
                dd["tuanzhang"] += (fee_vals[2] or Decimal("0"))   # 团长(负)
    finally:
        wb.close()

    # 周期优先取文件名；否则回退核销时间跨度
    fn_start, fn_end = _period_from_filename(filename)
    p_start = fn_start or min_dt
    p_end = fn_end or max_dt

    period_text = ""
    if p_start and p_end:
        period_text = f"{p_start.year}/{p_start.month}/{p_start.day}-{p_end.year}/{p_end.month}/{p_end.day}"

    # **按日期粒度**逐日计算并舍入,再累加为期合计（精准默认值,供前端预填/可改）
    defs = daily_defaults(daily)

    return {
        "supplier_received": _q(supplier_received),
        "suggested_commission": defs["commission"],
        "def_hexiao": defs["hexiao"],
        "def_service_fee": defs["service_fee"],
        "def_jinying": defs["jinying"],
        "daily_json": serialize_daily(daily),
        "order_count": order_count,
        "positive_count": positive_count,
        "period_start": p_start,
        "period_end": p_end,
        "period_text": period_text,
        "check_date_text": period_text,
        "sheets": used_sheets,
    }


# --------------------------------------------------------------------------- #
# 逐日明细：序列化持久化 + 逐日重算（编辑改费率/佣金时仍按天累加，不退回总额×费率）
# --------------------------------------------------------------------------- #
def _days_from_daily(daily: dict[str, dict]) -> list[dict]:
    """按日聚合 dict → 逐日列表（Decimal）。"""
    return [{
        "recv": dd["received"], "shishou": dd["shishou"],
        "daren": dd["daren"], "tuanzhang": dd["tuanzhang"],
    } for dd in daily.values()]


def serialize_daily(daily: dict[str, dict]) -> str:
    """逐日明细序列化为 JSON（Decimal→字符串），随台账行持久化，供编辑时逐日重算。"""
    out = [{
        "r": str(dd["received"]), "s": str(dd["shishou"]),
        "d": str(dd["daren"]), "t": str(dd["tuanzhang"]),
    } for dd in daily.values()]
    return json.dumps(out, ensure_ascii=False)


def _days_from_json(daily_json: str) -> list[dict]:
    if not daily_json:
        return []
    try:
        raw = json.loads(daily_json)
    except (ValueError, TypeError):
        return []
    days = []
    for d in raw:
        days.append({
            "recv": _num(d.get("r")) or Decimal("0"),
            "shishou": _num(d.get("s")) or Decimal("0"),
            "daren": _num(d.get("d")) or Decimal("0"),
            "tuanzhang": _num(d.get("t")) or Decimal("0"),
        })
    return days


def _distribute_commission(days: list[dict], commission_override) -> tuple[list, Decimal]:
    """逐日自动佣金 = 实收×6%−达人−团长；若传入总额 override 且≠自动总额，
    则把差额按各天订单实收占比分摊到各天（微调场景，未改动时结果不变）。"""
    comm_auto = [_q(d["shishou"] * DEFAULT_COMMISSION_RATE + d["daren"] + d["tuanzhang"]) for d in days]
    c0 = _q(sum(comm_auto, Decimal("0")))
    if commission_override is None or abs((commission_override or Decimal("0")) - c0) < Decimal("0.005"):
        return comm_auto, c0
    delta = commission_override - c0
    s_total = sum((d["shishou"] for d in days), Decimal("0"))
    n = len(days) or 1
    comm_day = []
    for i, d in enumerate(days):
        share = (d["shishou"] / s_total) if s_total > 0 else (Decimal("1") / n)
        comm_day.append(_q(comm_auto[i] + delta * share))
    return comm_day, _q(commission_override)


def recompute_from_days(days: list[dict],
                        rate_hexiao: Decimal = DEFAULT_RATE_HEXIAO,
                        rate_settle: Decimal = DEFAULT_RATE_SETTLE,
                        commission_override=None) -> dict | None:
    """门票逐日重算并累加（逐日舍入到分）：出版应得B_day=到账−佣金；
    核销=B_day×核销率、结算=B_day×结算费率、服务费=结算−核销，各自逐日累加。"""
    if not days:
        return None
    comm_day, c_total = _distribute_commission(days, commission_override)
    hexiao = jinying = pub = Decimal("0")
    for i, d in enumerate(days):
        b = d["recv"] - comm_day[i]
        pub += b
        hexiao += _q(b * rate_hexiao)
        jinying += _q(b * rate_settle)
    return {
        "supplier_commission": _q(c_total),
        "publisher_due": _q(pub),
        "hexiao_amount": _q(hexiao),
        "service_fee": _q(jinying - hexiao),
        "jinying_amount": _q(jinying),
    }


def recompute_from_json(daily_json: str,
                        rate_hexiao: Decimal = DEFAULT_RATE_HEXIAO,
                        rate_settle: Decimal = DEFAULT_RATE_SETTLE,
                        commission_override=None) -> dict | None:
    return recompute_from_days(_days_from_json(daily_json), rate_hexiao, rate_settle, commission_override)


def daily_defaults(daily: dict[str, dict],
                   rate_hexiao: Decimal = DEFAULT_RATE_HEXIAO,
                   rate_settle: Decimal = DEFAULT_RATE_SETTLE) -> dict:
    """解析时的按日精准默认值（佣金取逐日自动值）。"""
    res = recompute_from_days(_days_from_daily(daily), rate_hexiao, rate_settle, None)
    if res is None:
        return {"commission": Decimal("0"), "hexiao": Decimal("0"),
                "service_fee": Decimal("0"), "jinying": Decimal("0")}
    return {"commission": res["supplier_commission"], "hexiao": res["hexiao_amount"],
            "service_fee": res["service_fee"], "jinying": res["jinying_amount"]}


def compute_row(
    supplier_received: Decimal,
    supplier_commission: Decimal = Decimal("0"),
    rate_hexiao: Decimal = DEFAULT_RATE_HEXIAO,
    rate_settle: Decimal = DEFAULT_RATE_SETTLE,
) -> dict:
    """由服务商到账、服务商佣金与比例计算台账计算列。

      出版应得到账金额 B = 服务商到账 - 服务商佣金
      景区核销金额 = B × 核销率
      结算金额     = B × 结算费率
      服务费       = 结算金额 − 景区核销金额
    """
    received = supplier_received or Decimal("0")
    commission = supplier_commission or Decimal("0")
    b = received - commission
    hexiao = _q(b * rate_hexiao)
    jinying = _q(b * rate_settle)
    fee = _q(jinying - hexiao)
    return {
        "supplier_commission": _q(commission),
        "publisher_due": _q(b),        # 出版应得到账金额 = 服务商到账 - 服务商佣金
        "hexiao_amount": hexiao,       # 景区核销金额
        "service_fee": fee,            # 服务费 = 结算金额 − 景区核销金额
        "jinying_amount": jinying,     # 结算金额 = B × 结算费率
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
# 注：付款金额不在生成台账中展示（仅待确认台账录入 + 参与后端递推），故导出亦不含该列。
_EXPORT_HEADERS = [
    "平台", "景区门票", "核对日期",
    "景区核销金额", "景区待核销金额", "结算金额", "服务费",
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
        float(_q(sum_hexiao)), float(_q(sum_pending)),
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
    widths = [8, 22, 20, 15, 15, 15, 14, 13, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
