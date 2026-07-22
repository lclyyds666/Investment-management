"""文旅业务·景区酒店平台核销台账计算服务（泉州欧乐堡）。

解析一份对账明细 xlsx（含抖音/美团/携程多平台、每平台多张周明细表），
按平台聚合出「结算基数 / 间夜 / 服务商到账·佣金(抖音)」，供前端确认后生成台账。

平台计算口径（已用真实业务台账 6 期反推验证）：
- 抖音(71列, 与门票同构; 列名跨期漂移, 按别名匹配)：
    服务商到账 = −Σ(服务商服务费|服务商佣金) = Σ(订单实收−软件−达人−团长)
    服务商佣金(默认) = 订单实收×6% − 达人服务费 − 团长服务费 (达人/团长为负,相加=减)
    结算基数(出版应得) = 到账 − 佣金
- 美团(26列)：结算基数 = Σ结算金额
- 携程(24列)：结算基数 = Σ结算价
统一：景区核销 = 结算基数 × 核销率(0.9)；服务费 = 间夜 × 44；结算金额 = 核销 + 服务费。
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO

import openpyxl

DEFAULT_RATE_HEXIAO = Decimal("0.90")     # 景区核销率
DEFAULT_FEE_PER_NIGHT = Decimal("44.00")  # 每间夜服务费
DEFAULT_COMMISSION_RATE = Decimal("0.06")  # 抖音服务商佣金率(对订单实收)
_CENT = Decimal("0.01")

# 平台识别（按 sheet 标题前缀）
PLATFORMS = ("抖音", "美团", "携程")

# 列别名（跨期/跨平台容错）
COL_DY_SHISHOU = {"订单实收金额"}
COL_DY_RUANJIAN = {"软件服务费"}
COL_DY_DAREN = {"达人服务费", "达人佣金"}
COL_DY_TUANZHANG = {"团长服务费", "撮合经纪服务费"}
COL_DY_FUWUSHANG = {"服务商服务费", "服务商佣金"}
COL_DY_NIGHTS = {"间夜", "间夜数"}
COL_DY_TIME = {"核销时间"}
COL_MT_JIESUAN = {"结算金额"}
COL_MT_NIGHTS = {"间夜"}
COL_MT_CHECKIN = {"入住日期"}
COL_XC_JIESUAN = {"结算价"}
COL_XC_NIGHTS = {"间夜"}
COL_XC_CHECKIN = {"入住日期"}


def _num(v):
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
    return (v or Decimal("0")).quantize(_CENT, rounding=ROUND_HALF_UP)


def _to_date(v):
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


def _idx(header: list, names: set[str]) -> int:
    for i, h in enumerate(header):
        if h is not None and str(h).strip() in names:
            return i
    return -1


def _platform_of(title: str) -> str | None:
    t = title or ""
    for p in PLATFORMS:
        if t.startswith(p) or p in t[:4]:
            return p
    return None


def _year_from_filename(filename: str) -> int | None:
    m = re.search(r"(20\d{2})", filename or "")
    return int(m.group(1)) if m else None


def _dates_from_title(title: str, year: int | None) -> tuple[date | None, date | None]:
    """从 sheet 标题解析日期跨度，如 '携程6.15-6.21' / '抖音明细1.14-1.20'。"""
    if not year:
        return None, None
    md = re.findall(r"(\d{1,2})[.\-=](\d{1,2})", title or "")
    ds = []
    for mo, dy in md:
        try:
            ds.append(date(year, int(mo), int(dy)))
        except ValueError:
            continue
    if not ds:
        return None, None
    return min(ds), max(ds)


def _header_row(rows_iter) -> tuple[list, list]:
    """返回 (header, remaining_rows_list)。header=首个非空行。"""
    rows = list(rows_iter)
    hi = 0
    for i, r in enumerate(rows):
        if r and any(c is not None and str(c).strip() for c in r):
            hi = i
            break
    header = [("" if c is None else str(c).strip()) for c in rows[hi]]
    return header, rows[hi + 1:]


def _col_sum(rows: list, i: int) -> Decimal:
    if i < 0:
        return Decimal("0")
    s = Decimal("0")
    for r in rows:
        v = _num(r[i]) if i < len(r) else None
        if v is not None:
            s += v
    return s


def _count_rows(rows: list, key_idx: int) -> int:
    n = 0
    for r in rows:
        if key_idx < 0:
            if r and any(c is not None and str(c).strip() for c in r):
                n += 1
        elif key_idx < len(r) and r[key_idx] is not None and str(r[key_idx]).strip():
            n += 1
    return n


def parse_hotel_file(content: bytes, filename: str = "") -> dict:
    """解析一份酒店对账明细，按平台聚合。返回 {"platforms": [platform_info...], "warnings": [...]}。"""
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True, read_only=True)
    year = _year_from_filename(filename)
    agg: dict[str, dict] = {}
    warnings: list[str] = []

    try:
        for ws in wb.worksheets:
            plat = _platform_of(ws.title)
            if plat is None:
                continue
            header, rows = _header_row(ws.iter_rows(values_only=True))
            d = agg.setdefault(plat, {
                "platform": plat, "room_nights": 0, "order_count": 0,
                "base_received": Decimal("0"), "shishou": Decimal("0"),
                "daren": Decimal("0"), "tuanzhang": Decimal("0"),
                "pstart": None, "pend": None,
            })
            # 周期：优先 sheet 标题，回退明细日期列
            s0, e0 = _dates_from_title(ws.title, year)

            if plat == "抖音":
                i_fs = _idx(header, COL_DY_FUWUSHANG)
                i_shi = _idx(header, COL_DY_SHISHOU)
                i_ruan = _idx(header, COL_DY_RUANJIAN)
                i_da = _idx(header, COL_DY_DAREN)
                i_tu = _idx(header, COL_DY_TUANZHANG)
                i_night = _idx(header, COL_DY_NIGHTS)
                i_time = _idx(header, COL_DY_TIME)
                # 服务商到账 = −Σ服务商服务费；无该列则回退 实收−软件−达人−团长
                if i_fs >= 0:
                    d["base_received"] += -_col_sum(rows, i_fs)
                else:
                    d["base_received"] += (_col_sum(rows, i_shi) + _col_sum(rows, i_ruan)
                                           + _col_sum(rows, i_da) + _col_sum(rows, i_tu))
                d["shishou"] += _col_sum(rows, i_shi)
                d["daren"] += _col_sum(rows, i_da)
                d["tuanzhang"] += _col_sum(rows, i_tu)
                d["room_nights"] += int(_col_sum(rows, i_night))
                d["order_count"] += _count_rows(rows, i_shi)
                if (s0 is None or e0 is None) and i_time >= 0:
                    ds = [x for x in (_to_date(r[i_time]) for r in rows if i_time < len(r)) if x]
                    if ds:
                        s0 = s0 or min(ds); e0 = e0 or max(ds)
            elif plat == "美团":
                i_j = _idx(header, COL_MT_JIESUAN)
                i_night = _idx(header, COL_MT_NIGHTS)
                d["base_received"] += _col_sum(rows, i_j)
                d["room_nights"] += int(_col_sum(rows, i_night))
                d["order_count"] += _count_rows(rows, i_j)
            elif plat == "携程":
                i_j = _idx(header, COL_XC_JIESUAN)
                i_night = _idx(header, COL_XC_NIGHTS)
                d["base_received"] += _col_sum(rows, i_j)
                d["room_nights"] += int(_col_sum(rows, i_night))
                d["order_count"] += _count_rows(rows, i_j)

            if s0:
                d["pstart"] = s0 if d["pstart"] is None else min(d["pstart"], s0)
            if e0:
                d["pend"] = e0 if d["pend"] is None else max(d["pend"], e0)
    finally:
        wb.close()

    out = []
    for plat in PLATFORMS:
        if plat not in agg:
            continue
        d = agg[plat]
        base_received = _q(d["base_received"])
        # 抖音佣金默认值 = 订单实收×6% − 达人 − 团长（达人/团长为负,相加=减）
        commission = Decimal("0")
        if plat == "抖音":
            commission = _q(d["shishou"] * DEFAULT_COMMISSION_RATE + d["daren"] + d["tuanzhang"])
        p_text = ""
        if d["pstart"] and d["pend"]:
            s, e = d["pstart"], d["pend"]
            p_text = f"{s.year}/{s.month}/{s.day}-{e.year}/{e.month}/{e.day}"
        if d["order_count"] == 0:
            warnings.append(f"{plat}：未解析到有效明细")
        out.append({
            "platform": plat,
            "room_nights": d["room_nights"],
            "order_count": d["order_count"],
            "base_received": base_received,
            "suggested_commission": commission,
            "period_start": d["pstart"],
            "period_end": d["pend"],
            "period_text": p_text,
            "check_date_text": p_text,
        })
    return {"platforms": out, "warnings": warnings}


def compute_row(
    platform: str,
    base_received: Decimal,
    supplier_commission: Decimal,
    room_nights: int,
    rate_hexiao: Decimal = DEFAULT_RATE_HEXIAO,
    fee_per_night: Decimal = DEFAULT_FEE_PER_NIGHT,
) -> dict:
    """由平台原值/佣金/间夜与比例计算台账列。"""
    recv = base_received or Decimal("0")
    comm = supplier_commission or Decimal("0")
    if platform != "抖音":
        comm = Decimal("0")  # 美团/携程无服务商佣金层
    settle_base = recv - comm
    hexiao = _q(settle_base * rate_hexiao)
    fee = _q(Decimal(int(room_nights or 0)) * (fee_per_night or Decimal("0")))
    jinying = _q(hexiao + fee)
    return {
        "supplier_commission": _q(comm),
        "settle_base": _q(settle_base),
        "hexiao_amount": hexiao,
        "service_fee": fee,
        "jinying_amount": jinying,
    }


def running_pending(prev_balance: Decimal, payment_amount: Decimal, hexiao_amount: Decimal) -> Decimal:
    """期次递推：本期待核销 = 上期余额 + 本期付款 − 本期核销（首期 prev=0）。按平台各自滚动。"""
    prev = prev_balance or Decimal("0")
    pay = payment_amount or Decimal("0")
    hexiao = hexiao_amount or Decimal("0")
    return _q(prev + pay - hexiao)


# —— 导出（台账列不含付款金额；含合计）——
_EXPORT_HEADERS = [
    "平台", "酒店名称", "核对日期",
    "景区核销金额", "景区待核销金额", "结算金额", "服务费", "间夜",
    "回款日期", "回款金额",
]


def _fmt_date(v) -> str:
    if not v:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return str(v)


def _fa(v):
    d = _num(v)
    return float(_q(d)) if d is not None else ""


def build_export_workbook(rows: list[dict], title: str = "酒店平台业务台账") -> bytes:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "酒店平台业务台账"
    ncol = len(_EXPORT_HEADERS)
    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    tc = ws.cell(row=1, column=1, value=title)
    tc.font = Font(size=13, bold=True); tc.alignment = center

    head_fill = PatternFill("solid", fgColor="DCE6F1")
    for c, name in enumerate(_EXPORT_HEADERS, start=1):
        cell = ws.cell(row=2, column=c, value=name)
        cell.font = Font(bold=True); cell.alignment = center; cell.fill = head_fill; cell.border = border

    s_hx = s_jy = s_fee = Decimal("0"); s_night = 0; s_repay = Decimal("0")
    r = 3
    for row in rows:
        vals = [
            row.get("platform", ""), row.get("hotel_name", ""), row.get("check_date_text", ""),
            _fa(row.get("hexiao_amount")), _fa(row.get("pending_writeoff")),
            _fa(row.get("jinying_amount")), _fa(row.get("service_fee")),
            int(row.get("room_nights") or 0),
            _fmt_date(row.get("repay_date")), _fa(row.get("repay_amount")),
        ]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=c, value=v); cell.alignment = center; cell.border = border
        s_hx += _num(row.get("hexiao_amount")) or Decimal("0")
        s_jy += _num(row.get("jinying_amount")) or Decimal("0")
        s_fee += _num(row.get("service_fee")) or Decimal("0")
        s_night += int(row.get("room_nights") or 0)
        s_repay += _num(row.get("repay_amount")) or Decimal("0")
        r += 1

    total_fill = PatternFill("solid", fgColor="FDE9D9")
    total_vals = ["合计", "", "", float(_q(s_hx)), "", float(_q(s_jy)), float(_q(s_fee)), s_night, "", float(_q(s_repay))]
    for c, v in enumerate(total_vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font = Font(bold=True); cell.alignment = center; cell.fill = total_fill; cell.border = border

    for i, wd in enumerate([8, 30, 20, 15, 15, 15, 13, 8, 13, 14], start=1):
        ws.column_dimensions[get_column_letter(i)].width = wd

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
