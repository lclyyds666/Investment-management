"""文旅业务·景区酒店平台核销业务台账端点（按 scenic_id 严格数据隔离）。

链路：上传单个对账明细(=一期,含多平台)→解析按平台聚合(parse,落盘源文件,不落台账)
     → 前端确认(可改抖音佣金/间夜/回款/付款金额)→ 保存落库(save,按平台重算滚动余额)
     → 列表/编辑/删除 → 导出。
待核销余额按「平台」各自滚动（沿用门票台账逻辑，一平台=一个结算账户）。
"""
import asyncio
import io
import uuid
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.hotel_ledger import HotelLedger
from app.models.user import User
from app.schemas.common import Response
from app.schemas.hotel_ledger import (
    HotelLedgerOut,
    HotelLedgerRow,
    HotelSaveIn,
    HotelTotals,
    HotelUpdateIn,
    ParsedPlatform,
    ParseResult,
)
from app.services import hotel_ledger as hl_svc

router = APIRouter()

_XLSX_EXT = {".xlsx", ".xls"}
_MAX_BYTES = 30 * 1024 * 1024
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PARSE_SEMAPHORE = asyncio.Semaphore(1)


def _valid_scenic_id(scenic_id: str) -> str:
    sid = (scenic_id or "").strip()
    if not sid or len(sid) > 64:
        raise HTTPException(status_code=400, detail="景区标识(scenic_id)非法")
    return sid


def _detail_dir(sid: str) -> Path:
    return Path(settings.UPLOAD_DIR) / f"hotel_detail_{sid}"


def _row_out(r: HotelLedger) -> HotelLedgerRow:
    return HotelLedgerRow.model_validate(r)


def _load_rows(db: Session, sid: str) -> list[HotelLedger]:
    """按核对日期(period_start)升序，再平台名、row_no 稳定排序。"""
    return db.scalars(
        select(HotelLedger)
        .where(HotelLedger.scenic_id == sid)
        .order_by(
            HotelLedger.period_start.is_(None),
            HotelLedger.period_start.asc(),
            HotelLedger.platform.asc(),
            HotelLedger.row_no.asc(),
            HotelLedger.id.asc(),
        )
    ).all()


def _period_key(r: HotelLedger) -> str:
    """一期标识（一份对账明细=一期）；与前端 displayRows 分组键一致。"""
    return r.source_file or r.detail_name or r.period_text or r.check_date_text or "NA"


def _group_periods(rows: list[HotelLedger]) -> tuple[dict[str, list[HotelLedger]], list[str]]:
    """按期分组，保持传入顺序（rows 须已按 period_start 升序 → order 即期次先后）。"""
    groups: dict[str, list[HotelLedger]] = {}
    order: list[str] = []
    for r in rows:
        k = _period_key(r)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    return groups, order


def _totals(rows: list[HotelLedger]) -> HotelTotals:
    def s(attr):
        return sum((getattr(x, attr) or Decimal("0") for x in rows), Decimal("0"))

    # 付款/回款每期各平台共享 → 每期只取一次；待核销为整期滚动余额 → 合计取末期余额
    groups, order = _group_periods(rows)
    payment = Decimal("0")
    repay = Decimal("0")
    for k in order:
        grp = groups[k]
        payment += max((g.payment_amount or Decimal("0") for g in grp), default=Decimal("0"))
        reps = [g.repay_amount for g in grp if g.repay_amount is not None]
        if reps:
            repay += reps[0]
    pending = (groups[order[-1]][0].pending_writeoff or Decimal("0")) if order else Decimal("0")

    return HotelTotals(
        hexiao_amount=s("hexiao_amount"),
        jinying_amount=s("jinying_amount"),
        service_fee=s("service_fee"),
        payment_amount=payment,
        pending_writeoff=pending,
        room_nights=sum((r.room_nights or 0 for r in rows), 0),
        repay_amount=repay,
    )


def _recompute_running_balance(rows: list[HotelLedger]) -> None:
    """按**整期**滚动重算待核销余额。rows 须按 period_start 升序。

    本期待核销 = 上期待核销 + 本期付款(每期共享) − 本期各平台核销合计；写回该期各行。
    """
    groups, order = _group_periods(rows)
    prev = Decimal("0")
    for k in order:
        grp = groups[k]
        pay = max((g.payment_amount or Decimal("0") for g in grp), default=Decimal("0"))
        hexiao_sum = sum((g.hexiao_amount or Decimal("0") for g in grp), Decimal("0"))
        cur = hl_svc.running_pending(prev, pay, hexiao_sum)
        for g in grp:
            g.pending_writeoff = cur
        prev = cur


# --------------------------------------------------------------------------- #
# 1) 上传单文件 → 按平台解析（不落台账；源文件落盘）
# --------------------------------------------------------------------------- #
@router.post(
    "/{scenic_id}/hotel-ledger/parse",
    response_model=Response[ParseResult],
    summary="上传对账明细(单文件=一期,含多平台)并解析",
)
async def parse_file(
    scenic_id: str,
    files: list[UploadFile] = File(..., description="对账明细 Excel(.xlsx/.xls)，每次仅 1 个"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    if len(files) != 1:
        raise HTTPException(status_code=400, detail="每次仅能上传 1 个对账明细文件（1 文件=1 期，内含多平台）")
    f = files[0]
    fname = f.filename or "对账明细.xlsx"
    ext = Path(fname).suffix.lower()
    if ext not in _XLSX_EXT:
        raise HTTPException(status_code=400, detail="仅支持 Excel(.xlsx/.xls)")
    content = await f.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 30MB 上限")

    detail_stored = ""
    try:
        d = _detail_dir(sid)
        d.mkdir(parents=True, exist_ok=True)
        detail_stored = f"{uuid.uuid4().hex}{ext}"
        (d / detail_stored).write_bytes(content)
    except OSError:
        detail_stored = ""

    try:
        async with _PARSE_SEMAPHORE:
            info = await run_in_threadpool(hl_svc.parse_hotel_file, content, fname)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"解析失败：{exc}")
    finally:
        del content

    platforms = [ParsedPlatform(**p) for p in info["platforms"]]
    if not platforms:
        raise HTTPException(status_code=400, detail="未识别到抖音/美团/携程任一平台的明细数据")
    return Response.ok(
        ParseResult(
            scenic_id=sid, source_file=fname,
            detail_stored=detail_stored, detail_name=fname,
            platforms=platforms, warnings=info["warnings"],
        ),
        message=f"解析完成：本期识别 {len(platforms)} 个平台",
    )


# --------------------------------------------------------------------------- #
# 2) 查询台账
# --------------------------------------------------------------------------- #
@router.get(
    "/{scenic_id}/hotel-ledger",
    response_model=Response[HotelLedgerOut],
    summary="查询某景区酒店平台业务台账",
)
def get_ledger(scenic_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    sid = _valid_scenic_id(scenic_id)
    rows = _load_rows(db, sid)
    return Response.ok(HotelLedgerOut(
        scenic_id=sid, rows=[_row_out(r) for r in rows], totals=_totals(rows), total=len(rows),
    ))


# --------------------------------------------------------------------------- #
# 3) 保存台账（落库 + 按平台重算滚动余额）
# --------------------------------------------------------------------------- #
@router.post(
    "/{scenic_id}/hotel-ledger",
    response_model=Response[HotelLedgerOut],
    summary="保存酒店平台业务台账(确认后落库)",
)
def save_ledger(
    scenic_id: str,
    payload: HotelSaveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    if payload.mode == "replace":
        db.execute(sa_delete(HotelLedger).where(HotelLedger.scenic_id == sid))
        base_no = 0
    else:
        base_no = db.scalar(
            select(HotelLedger.row_no).where(HotelLedger.scenic_id == sid)
            .order_by(HotelLedger.row_no.desc()).limit(1)
        ) or 0

    for i, r in enumerate(payload.rows, start=1):
        # 逐日重算：有逐日明细则按天累加，否则回退期级公式
        calc = hl_svc.recompute_from_json(
            r.platform, r.daily_json, r.rate_hexiao, r.rate_settle,
            r.fee_per_night, r.fee_algo, r.supplier_commission,
        ) or hl_svc.compute_row(
            r.platform, r.base_received, r.supplier_commission,
            r.room_nights, r.rate_hexiao, r.fee_per_night, r.fee_algo, r.rate_settle,
        )
        db.add(HotelLedger(
            scenic_id=sid, row_no=base_no + i,
            platform=r.platform or "", hotel_name=r.hotel_name or "",
            check_date_text=r.check_date_text or "", period_text=r.period_text or "",
            period_start=r.period_start, period_end=r.period_end,
            room_nights=r.room_nights or 0,
            base_received=r.base_received or Decimal("0"),
            supplier_commission=calc["supplier_commission"],
            settle_base=calc["settle_base"],
            rate_hexiao=r.rate_hexiao,
            hexiao_amount=calc["hexiao_amount"],
            fee_algo=r.fee_algo or 1,
            fee_per_night=r.fee_per_night,
            rate_settle=r.rate_settle,
            service_fee=calc["service_fee"],
            jinying_amount=calc["jinying_amount"],   # 结算金额=逐日累加(派生,不手工覆盖)
            daily_json=r.daily_json or "",
            payment_amount=r.payment_amount or Decimal("0"),
            repay_date=r.repay_date, repay_amount=r.repay_amount,
            order_count=r.order_count or 0,
            source_file=r.source_file or "",
            detail_stored=r.detail_stored or "", detail_name=r.detail_name or r.source_file or "",
            uploaded_by=current_user.id,
        ))
    db.flush()
    _recompute_running_balance(_load_rows(db, sid))
    db.commit()

    rows = _load_rows(db, sid)
    return Response.ok(
        HotelLedgerOut(scenic_id=sid, rows=[_row_out(r) for r in rows], totals=_totals(rows), total=len(rows)),
        message=f"已保存 {len(payload.rows)} 行台账",
    )


# --------------------------------------------------------------------------- #
# 4) 编辑单行
# --------------------------------------------------------------------------- #
@router.put(
    "/{scenic_id}/hotel-ledger/{row_id}",
    response_model=Response[HotelLedgerRow],
    summary="编辑台账单行(佣金/核销率/每间夜服务费/间夜/付款/回款)",
)
def update_row(
    scenic_id: str, row_id: int, payload: HotelUpdateIn,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    row = db.scalar(select(HotelLedger).where(HotelLedger.id == row_id, HotelLedger.scenic_id == sid))
    if not row:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")

    if payload.hotel_name is not None:
        row.hotel_name = payload.hotel_name

    calc_dirty = False
    if payload.supplier_commission is not None:
        row.supplier_commission = payload.supplier_commission; calc_dirty = True
    if payload.rate_hexiao is not None:
        row.rate_hexiao = payload.rate_hexiao; calc_dirty = True
    if payload.fee_algo is not None:
        row.fee_algo = payload.fee_algo; calc_dirty = True
    if payload.fee_per_night is not None:
        row.fee_per_night = payload.fee_per_night; calc_dirty = True
    if payload.rate_settle is not None:
        row.rate_settle = payload.rate_settle; calc_dirty = True
    if payload.room_nights is not None:
        row.room_nights = payload.room_nights; calc_dirty = True
    if calc_dirty:
        # 逐日重算：改费率/佣金/算法也按天累加(有逐日明细时)，否则回退期级公式
        calc = hl_svc.recompute_from_json(
            row.platform, row.daily_json, row.rate_hexiao, row.rate_settle,
            row.fee_per_night, row.fee_algo, row.supplier_commission,
        ) or hl_svc.compute_row(
            row.platform, row.base_received, row.supplier_commission,
            row.room_nights, row.rate_hexiao, row.fee_per_night, row.fee_algo, row.rate_settle,
        )
        row.supplier_commission = calc["supplier_commission"]
        row.settle_base = calc["settle_base"]
        row.hexiao_amount = calc["hexiao_amount"]
        row.service_fee = calc["service_fee"]
        row.jinying_amount = calc["jinying_amount"]   # 结算金额=逐日累加(派生,不手工覆盖)

    # 付款金额 / 回款日期 / 回款金额：每期各平台共享 → 同步到本期所有平台行
    balance_dirty = calc_dirty
    if payload.payment_amount is not None or payload.repay_date is not None or payload.repay_amount is not None:
        for sib in _load_rows(db, sid):
            if _period_key(sib) != _period_key(row):
                continue
            if payload.payment_amount is not None:
                sib.payment_amount = payload.payment_amount
            if payload.repay_date is not None:
                sib.repay_date = payload.repay_date
            if payload.repay_amount is not None:
                sib.repay_amount = payload.repay_amount
        if payload.payment_amount is not None:
            balance_dirty = True

    db.flush()
    if balance_dirty:
        _recompute_running_balance(_load_rows(db, sid))
    db.commit()
    db.refresh(row)
    return Response.ok(_row_out(row), message="已更新")


# --------------------------------------------------------------------------- #
# 5) 删除单行 / 清空
# --------------------------------------------------------------------------- #
@router.delete(
    "/{scenic_id}/hotel-ledger/{row_id}",
    response_model=Response[dict],
    summary="删除台账单行",
)
def delete_row(scenic_id: str, row_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    sid = _valid_scenic_id(scenic_id)
    row = db.scalar(select(HotelLedger).where(HotelLedger.id == row_id, HotelLedger.scenic_id == sid))
    if not row:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")
    if row.detail_stored:
        try:
            fp = _detail_dir(sid) / Path(row.detail_stored).name
            if fp.exists():
                fp.unlink()
        except OSError:
            pass
    db.delete(row)
    db.flush()
    _recompute_running_balance(_load_rows(db, sid))
    db.commit()
    return Response.ok({"deleted": 1}, message="已删除")


@router.delete(
    "/{scenic_id}/hotel-ledger",
    response_model=Response[dict],
    summary="清空某景区酒店平台业务台账",
)
def clear_ledger(scenic_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    sid = _valid_scenic_id(scenic_id)
    result = db.execute(sa_delete(HotelLedger).where(HotelLedger.scenic_id == sid))
    db.commit()
    return Response.ok({"deleted": result.rowcount or 0}, message="已清空该景区酒店台账")


# --------------------------------------------------------------------------- #
# 6) 导出
# --------------------------------------------------------------------------- #
@router.get("/{scenic_id}/hotel-ledger/export", summary="导出酒店平台业务台账(.xlsx)")
def export_ledger(scenic_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    sid = _valid_scenic_id(scenic_id)
    rows = _load_rows(db, sid)
    if not rows:
        raise HTTPException(status_code=400, detail="该景区暂无台账数据，无法导出")
    export_rows = [{
        "platform": r.platform, "hotel_name": r.hotel_name, "check_date_text": r.check_date_text,
        "hexiao_amount": r.hexiao_amount, "pending_writeoff": r.pending_writeoff,
        "jinying_amount": r.jinying_amount, "service_fee": r.service_fee,
        "room_nights": r.room_nights, "repay_date": r.repay_date, "repay_amount": r.repay_amount,
        "period_key": r.source_file or r.detail_name or r.period_text or r.check_date_text or "",
    } for r in rows]
    data = hl_svc.build_export_workbook(export_rows, title=f"酒店平台业务台账-{sid}")
    fname = quote(f"酒店平台业务台账-{sid}.xlsx")
    return StreamingResponse(
        io.BytesIO(data), media_type=_XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )


# --------------------------------------------------------------------------- #
# 7) 明细源文件预览 / 下载
# --------------------------------------------------------------------------- #
@router.get("/{scenic_id}/hotel-ledger/detail", summary="预览/下载对账明细源文件")
def download_detail(
    scenic_id: str, stored: str, name: str = "",
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    safe = Path(stored or "").name
    if not safe:
        raise HTTPException(status_code=400, detail="缺少文件标识")
    path = _detail_dir(sid) / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="明细源文件不存在或已清理")
    return FileResponse(str(path), filename=name or safe, media_type=_XLSX_MIME)
