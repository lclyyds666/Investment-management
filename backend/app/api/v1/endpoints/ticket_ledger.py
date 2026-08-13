"""文旅业务·门票平台核销业务台账端点（严格按 scenic_id 数据隔离）。

数据作用域铁律（同 scenic.py）：
- scenic_id **一律取自 URL 路径**，不信任任何请求体传入的 scenic_id；
- 查询/删除/落库强制 `WHERE scenic_id = :sid`，每行 scenic_id 强制写为路径值；
- 任何接口都不会返回非当前 scenic_id 的数据。

链路：批量上传→逐文件解析算「服务商到账」+周期(parse，不落库)
     → 前端确认「出版应得B」/录手工字段 → 保存落库(save)
     → 列表/编辑/删除 → 导出标准格式业务台账 xlsx。
"""
import asyncio
import io
import mimetypes
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.config import settings
from app.core.enums import CompanyCode
from app.db.session import get_db
from app.models.ticket_ledger import TicketLedger
from app.models.user import User
from app.schemas.common import Response
from app.schemas.ticket_ledger import (
    ParsedFile,
    ParseResult,
    TicketLedgerCalculationPreview,
    TicketLedgerOut,
    TicketLedgerRow,
    TicketLedgerSaveIn,
    TicketLedgerTotals,
    TicketLedgerUpdateIn,
)
from app.services import ticket_ledger as tl_svc
from app.services.scenic_config import get_effective_config
from app.services.assignment_permissions import PermissionContext

router = APIRouter()

_XLSX_EXT = {".xlsx", ".xls"}
_MAX_BYTES = 30 * 1024 * 1024  # ≤ 30MB（明细可能上万行）
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 解析并发闸：小内存机(1.6GB)上，大文件解析(万行明细)峰值资源高。
# 限制同一时刻只跑 1 个解析，重叠上传排队而非叠加 → 防 OOM 僵死。
_PARSE_SEMAPHORE = asyncio.Semaphore(1)

# 台账变更(上传/保存/编辑/删除)角色：业务经办 + 信息维护(超管始终放行)
_supply_context = lambda: PermissionContext(company_code=CompanyCode.SUPPLY_MANAGEMENT.value)
_view_guard = require_permission("supply.scenic.view", _supply_context)
_create_guard = require_permission("supply.scenic.create", _supply_context)
_update_guard = require_permission("supply.scenic.update", _supply_context)
_delete_guard = require_permission("supply.scenic.delete", _supply_context)
_confirm_guard = require_permission("supply.scenic.review", _supply_context)
_download_guard = require_permission("supply.scenic.export", _supply_context)
_CONFIRM_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx"}
_CONFIRM_MAX_BYTES = 20 * 1024 * 1024


def _period_key(r: TicketLedger) -> str:
    """一期标识（一份对账明细=一期）；与前端 displayRows 分组键一致。"""
    return r.source_file or r.detail_name or r.period_text or r.check_date_text or "NA"


def _confirm_dir(sid: str) -> Path:
    return Path(settings.UPLOAD_DIR) / f"ticket_confirm_{sid}"


def _valid_scenic_id(scenic_id: str) -> str:
    sid = (scenic_id or "").strip()
    if not sid or len(sid) > 64:
        raise HTTPException(status_code=400, detail="景区标识(scenic_id)非法")
    return sid


def _row_out(r: TicketLedger) -> TicketLedgerRow:
    return TicketLedgerRow.model_validate(r)


def _recover_daily_json(row: TicketLedger) -> str:
    if row.daily_json:
        return row.daily_json
    stored = Path(row.detail_stored or "").name
    if not stored:
        raise HTTPException(
            status_code=409,
            detail="该门票台账缺少逐日明细和原始文件，无法按新佣金率精确重算",
        )
    source_path = _detail_dir(row.scenic_id) / stored
    if not source_path.is_file():
        raise HTTPException(
            status_code=409,
            detail="该门票台账的原始明细文件不存在，无法按新佣金率精确重算",
        )
    try:
        info = tl_svc.parse_reconciliation(
            source_path.read_bytes(),
            filename=row.detail_name or row.source_file or stored,
            scenic_id=row.scenic_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=409, detail=f"恢复逐日明细失败：{exc}") from exc
    platform_info = next(
        (
            item for item in info.get("platforms", [])
            if item.get("platform") == (row.platform or "抖音")
        ),
        info,
    )
    daily_json = platform_info.get("daily_json") or ""
    if not daily_json:
        raise HTTPException(status_code=409, detail="原始文件未解析出逐日明细，无法精确重算")
    return daily_json


def _effective_ticket_calculation(
    row: TicketLedger, payload: TicketLedgerUpdateIn
) -> tuple[dict, str]:
    platform = payload.platform if payload.platform is not None else (row.platform or "抖音")
    supplier_received = (
        payload.supplier_received
        if payload.supplier_received is not None
        else (row.supplier_received or Decimal("0"))
    )
    commission_rate = (
        payload.commission_rate
        if payload.commission_rate is not None
        else (
            row.commission_rate
            if row.commission_rate is not None
            else tl_svc.DEFAULT_COMMISSION_RATE
        )
    )
    rate_hexiao = payload.rate_hexiao if payload.rate_hexiao is not None else row.rate_hexiao
    rate_settle = payload.rate_settle if payload.rate_settle is not None else row.rate_settle
    received_changed = (
        payload.supplier_received is not None
        and abs(payload.supplier_received - (row.supplier_received or Decimal("0"))) > Decimal("0.005")
    )
    commission_rate_changed = (
        payload.commission_rate is not None
        and abs(payload.commission_rate - (row.commission_rate or Decimal("0"))) > Decimal("0.00005")
    )
    platform_changed = payload.platform is not None and payload.platform != row.platform
    daily_json = row.daily_json or ""
    if platform == "抖音" and (commission_rate_changed or platform_changed) and not daily_json:
        daily_json = _recover_daily_json(row)

    snapshot_calc = tl_svc.recompute_from_json(
        daily_json,
        rate_hexiao,
        rate_settle,
        None,
        commission_rate,
        platform,
        scenic_id=row.scenic_id,
    )
    daily_calc = snapshot_calc
    commission_override = payload.supplier_commission
    if (
        commission_override is None
        and platform == "抖音"
        and not commission_rate_changed
        and not platform_changed
        and snapshot_calc is not None
        and abs(snapshot_calc["supplier_commission"] - (row.supplier_commission or Decimal("0")))
        > Decimal("0.005")
    ):
        commission_override = row.supplier_commission
    if commission_override is not None:
        daily_calc = tl_svc.recompute_from_json(
            daily_json,
            rate_hexiao,
            rate_settle,
            commission_override,
            commission_rate,
            platform,
            scenic_id=row.scenic_id,
        )
    snapshot_matches_received = False
    if snapshot_calc is not None:
        snapshot_received = snapshot_calc["publisher_due"] + snapshot_calc["supplier_commission"]
        snapshot_matches_received = (
            abs(snapshot_received - supplier_received) <= Decimal("0.005")
        )
    if daily_calc is not None and snapshot_matches_received and not received_changed:
        return daily_calc, daily_json

    commission = (
        payload.supplier_commission
        if payload.supplier_commission is not None
        else (row.supplier_commission or Decimal("0"))
    )
    if (
        platform == "抖音"
        and commission_rate_changed
        and payload.supplier_commission is None
        and snapshot_calc is not None
    ):
        commission = snapshot_calc["supplier_commission"]
    return (
        tl_svc.compute_row(
            supplier_received,
            commission,
            rate_hexiao,
            rate_settle,
            platform,
            scenic_id=row.scenic_id,
        ),
        "" if received_changed or snapshot_calc is not None else daily_json,
    )


def _calculation_preview(
    row: TicketLedger, payload: TicketLedgerUpdateIn
) -> TicketLedgerCalculationPreview:
    commission_rate = (
        payload.commission_rate
        if payload.commission_rate is not None
        else (
            row.commission_rate
            if row.commission_rate is not None
            else tl_svc.DEFAULT_COMMISSION_RATE
        )
    )
    calc, _ = _effective_ticket_calculation(row, payload)
    hexiao_amount = (
        payload.hexiao_amount if payload.hexiao_amount is not None else calc["hexiao_amount"]
    )
    jinying_amount = (
        payload.jinying_amount if payload.jinying_amount is not None else calc["jinying_amount"]
    )
    return TicketLedgerCalculationPreview(
        supplier_commission=calc["supplier_commission"],
        commission_rate=commission_rate,
        publisher_due=calc["publisher_due"],
        hexiao_amount=hexiao_amount,
        jinying_amount=jinying_amount,
        service_fee=jinying_amount - hexiao_amount,
    )


def _totals(rows: list[TicketLedger]) -> TicketLedgerTotals:
    def s(attr):
        return sum((getattr(x, attr) or Decimal("0") for x in rows), Decimal("0"))

    groups: dict[str, list[TicketLedger]] = {}
    order: list[str] = []
    for row in rows:
        key = _period_key(row)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    payment = sum(
        (max((row.payment_amount or Decimal("0") for row in groups[key]), default=Decimal("0")) for key in order),
        Decimal("0"),
    )
    co_investment = sum(
        (max((row.co_investment_amount or Decimal("0") for row in groups[key]), default=Decimal("0")) for key in order),
        Decimal("0"),
    )
    repay = Decimal("0")
    for key in order:
        values = [row.repay_amount for row in groups[key] if row.repay_amount is not None]
        if values:
            repay += values[0]
    pending = (
        groups[order[-1]][0].pending_writeoff or Decimal("0") if order else Decimal("0")
    )

    return TicketLedgerTotals(
        hexiao_amount=s("hexiao_amount"),
        payment_amount=payment,
        co_investment_amount=co_investment,
        # 同一期可能有多个平台；待核销是整期滚动余额，取末期共享值。
        pending_writeoff=pending,
        jinying_amount=s("jinying_amount"),
        service_fee=s("service_fee"),
        publisher_due=s("publisher_due"),
        repay_amount=repay,
    )


def _load_rows(db: Session, sid: str) -> list[TicketLedger]:
    """按「核对日期(对账周期起) 升序」返回：最早的即第一期。
    period_start 为空的行排在最后，再按 row_no/id 兜底稳定排序。
    该顺序同时作为期次递推(滚动余额)的计算顺序。"""
    return db.scalars(
        select(TicketLedger)
        .where(TicketLedger.scenic_id == sid)
        .order_by(
            TicketLedger.period_start.is_(None),  # NULL(=1) 排最后
            TicketLedger.period_start.asc(),
            TicketLedger.row_no.asc(),
            TicketLedger.id.asc(),
        )
    ).all()


def _recompute_running_balance(rows: list[TicketLedger]) -> None:
    """按整期集中重算「景区待核销金额」滚动余额。

    同一源文件中的多个平台共享一期余额：付款只取一次，核销金额按平台求和。
    """
    if not rows:
        return
    balances = tl_svc.calculate_running_balances(
        rows[0].scenic_id, rows, group_by=_period_key
    )
    for r, balance in zip(rows, balances):
        r.pending_writeoff = balance


def _detail_dir(sid: str) -> Path:
    """某景区对账明细源文件落盘目录（供预览/下载）。"""
    return Path(settings.UPLOAD_DIR) / f"ticket_detail_{sid}"


# --------------------------------------------------------------------------- #
# 1) 批量上传 → 解析（不落库）
# --------------------------------------------------------------------------- #
@router.post(
    "/{scenic_id}/ticket-ledger/parse",
    response_model=Response[ParseResult],
    summary="上传对账明细并解析(单文件=一期，算服务商到账+周期，落盘源文件，不落台账)",
)
async def parse_files(
    scenic_id: str,
    files: list[UploadFile] = File(..., description="对账明细 Excel(.xlsx/.xls)，每次仅限 1 个"),
    db: Session = Depends(get_db),
    _: User = Depends(_create_guard),
):
    sid = _valid_scenic_id(scenic_id)
    config = get_effective_config(db, sid)
    # 单期逻辑：每次上传只允许 1 个文件，1 文件即计为一期
    if len(files) != 1:
        raise HTTPException(status_code=400, detail="每次仅能上传 1 个对账明细文件（1 个文件=1 期）")

    parsed: list[ParsedFile] = []
    warnings: list[str] = []
    failed = 0

    f = files[0]
    fname = f.filename or "对账明细.xlsx"
    ext = Path(fname).suffix.lower()
    if ext not in _XLSX_EXT:
        raise HTTPException(status_code=400, detail="仅支持 Excel(.xlsx/.xls)")
    content = await f.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 30MB 上限")

    # 源文件落盘（供预览/下载）：即使后续解析失败也保留，方便排查
    detail_stored = ""
    try:
        d = _detail_dir(sid)
        d.mkdir(parents=True, exist_ok=True)
        detail_stored = f"{uuid.uuid4().hex}{ext}"
        (d / detail_stored).write_bytes(content)
    except OSError:
        detail_stored = ""  # 落盘失败不阻断解析，仅无法预览/下载

    try:
        # 并发闸 + 线程池：CPU/内存密集的 openpyxl 解析不阻塞事件循环，
        # 且同一时刻只跑一个解析，避免重叠上传在小内存机上叠加 OOM。
        async with _PARSE_SEMAPHORE:
            info = await run_in_threadpool(
                tl_svc.parse_reconciliation, content, filename=fname, scenic_id=sid,
                rate_hexiao=config.ticket_rate_hexiao,
                rate_settle=config.ticket_rate_settle,
                commission_rate=config.ticket_commission_rate,
                commission_override=config.ticket_default_commission,
                ticket_product=config.default_ticket_product,
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"解析失败：{exc}")
    finally:
        del content  # 尽快释放大文件内存

    platform_results = info.get("platforms", [])
    if not platform_results:
        warnings.append(f"{fname}：未解析到有效核销明细，请确认文件内容")
    for platform_info in platform_results:
        if platform_info["order_count"] == 0:
            warnings.append(
                f"{fname}（{platform_info['platform']}）：未解析到有效核销明细"
            )
        parsed.append(ParsedFile(
            platform=platform_info["platform"],
            ticket_product=platform_info["ticket_product"],
            source_file=fname,
            detail_stored=detail_stored,
            detail_name=fname,
            supplier_received=platform_info["supplier_received"],
            suggested_commission=platform_info["suggested_commission"],
            commission_rate=platform_info["commission_rate"],
            rate_hexiao=platform_info["rate_hexiao"],
            rate_settle=platform_info["rate_settle"],
            def_hexiao=platform_info["def_hexiao"],
            def_service_fee=platform_info["def_service_fee"],
            def_jinying=platform_info["def_jinying"],
            daily_json=platform_info["daily_json"],
            order_count=platform_info["order_count"],
            positive_count=platform_info["positive_count"],
            period_text=platform_info["period_text"],
            check_date_text=platform_info["check_date_text"],
            period_start=platform_info["period_start"],
            period_end=platform_info["period_end"],
            sheets=platform_info["sheets"],
        ))

    return Response.ok(
        ParseResult(
            scenic_id=sid,
            files=parsed,
            succeeded=len(parsed),
            failed=failed,
            warnings=warnings,
        ),
        message=f"解析完成：本期识别 {len(parsed)} 个平台",
    )


# --------------------------------------------------------------------------- #
# 2) 查询台账（含合计）
# --------------------------------------------------------------------------- #
@router.get(
    "/{scenic_id}/ticket-ledger",
    response_model=Response[TicketLedgerOut],
    summary="查询某景区门票平台业务台账(仅该景区)",
)
def get_ledger(
    scenic_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    sid = _valid_scenic_id(scenic_id)
    rows = _load_rows(db, sid)
    return Response.ok(TicketLedgerOut(
        scenic_id=sid,
        rows=[_row_out(r) for r in rows],
        totals=_totals(rows),
        total=len(rows),
    ))


# --------------------------------------------------------------------------- #
# 3) 保存台账（落库；replace 覆盖 / append 追加）
# --------------------------------------------------------------------------- #
@router.post(
    "/{scenic_id}/ticket-ledger",
    response_model=Response[TicketLedgerOut],
    summary="保存业务台账(确认后落库，计算列由后端按B重算)",
)
def save_ledger(
    scenic_id: str,
    payload: TicketLedgerSaveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_create_guard),
):
    sid = _valid_scenic_id(scenic_id)
    config = get_effective_config(db, sid)

    if payload.mode == "replace":
        db.execute(sa_delete(TicketLedger).where(TicketLedger.scenic_id == sid))
        base_no = 0
    else:
        base_no = db.scalar(
            select(TicketLedger.row_no)
            .where(TicketLedger.scenic_id == sid)
            .order_by(TicketLedger.row_no.desc())
            .limit(1)
        ) or 0

    for i, r in enumerate(payload.rows, start=1):
        rate_hexiao = r.rate_hexiao if r.rate_hexiao is not None else config.ticket_rate_hexiao
        rate_settle = r.rate_settle if r.rate_settle is not None else config.ticket_rate_settle
        commission_rate = (
            r.commission_rate
            if r.commission_rate is not None
            else config.ticket_commission_rate
        )
        commission_override = (
            r.supplier_commission
            if r.supplier_commission is not None
            else config.ticket_default_commission
        )
        # 逐日重算：有逐日明细则按天累加(核销/结算/服务费逐日舍入再相加)，否则回退期级公式
        calc = tl_svc.recompute_from_json(
            r.daily_json, rate_hexiao, rate_settle, commission_override,
            commission_rate, r.platform or "抖音", scenic_id=sid
        ) or tl_svc.compute_row(
            r.supplier_received, commission_override or Decimal("0"), rate_hexiao, rate_settle,
            r.platform or "抖音", scenic_id=sid
        )
        # 结算金额可编辑：前端传入(手工改)则采用并令服务费=结算−核销；否则用逐日默认值
        if r.jinying_amount is not None:
            jinying_val = r.jinying_amount
            fee_val = r.jinying_amount - calc["hexiao_amount"]
        else:
            jinying_val = calc["jinying_amount"]
            fee_val = calc["service_fee"]
        db.add(TicketLedger(
            scenic_id=sid,                       # ← 铁律：作用域键来自路径
            row_no=base_no + i,
            pay_date=r.pay_date,
            platform=r.platform or "",
            ticket_product=r.ticket_product or config.default_ticket_product,
            check_date_text=r.check_date_text or "",
            period_text=r.period_text or "",
            period_start=r.period_start,
            period_end=r.period_end,
            supplier_received=r.supplier_received or Decimal("0"),
            supplier_commission=calc["supplier_commission"],
            commission_rate=commission_rate,
            publisher_due=calc["publisher_due"],
            hexiao_amount=calc["hexiao_amount"],
            payment_amount=r.payment_amount or Decimal("0"),
            co_investment_amount=r.co_investment_amount or Decimal("0"),
            jinying_amount=jinying_val,              # 结算金额(手工优先，否则逐日累加)
            service_fee=fee_val,                     # 服务费=结算−核销
            rate_hexiao=rate_hexiao,
            rate_settle=rate_settle,
            rate_fee=(r.rate_fee if r.rate_fee is not None else rate_settle - rate_hexiao),
            daily_json=r.daily_json or "",
            order_count=r.order_count or 0,
            positive_count=r.positive_count or 0,
            repay_date=r.repay_date,
            repay_amount=r.repay_amount,
            source_file=r.source_file or "",
            detail_stored=r.detail_stored or "",
            detail_name=r.detail_name or r.source_file or "",
            uploaded_by=current_user.id,
        ))
    db.flush()

    # 期次递推：集中重算全景区滚动余额（含新增期），避免多期重算混乱
    _recompute_running_balance(_load_rows(db, sid))
    db.commit()

    rows = _load_rows(db, sid)
    return Response.ok(
        TicketLedgerOut(
            scenic_id=sid,
            rows=[_row_out(r) for r in rows],
            totals=_totals(rows),
            total=len(rows),
        ),
        message=f"已保存 {len(payload.rows)} 行台账",
    )


# --------------------------------------------------------------------------- #
# 4) 编辑单行（回款/付款日期/平台/B 等，计算列随 B 重算）
# --------------------------------------------------------------------------- #
@router.post(
    "/{scenic_id}/ticket-ledger/{row_id}/preview",
    response_model=Response[TicketLedgerCalculationPreview],
    summary="预览编辑后的门票台账计算结果(不落库)",
)
def preview_update(
    scenic_id: str,
    row_id: int,
    payload: TicketLedgerUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(_update_guard),
):
    sid = _valid_scenic_id(scenic_id)
    row = db.scalar(
        select(TicketLedger).where(
            TicketLedger.id == row_id, TicketLedger.scenic_id == sid
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")
    return Response.ok(_calculation_preview(row, payload))


@router.put(
    "/{scenic_id}/ticket-ledger/{row_id}",
    response_model=Response[TicketLedgerRow],
    summary="编辑台账单行(回款/付款日期/平台/B等)",
)
def update_row(
    scenic_id: str,
    row_id: int,
    payload: TicketLedgerUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(_update_guard),
):
    sid = _valid_scenic_id(scenic_id)
    row = db.scalar(
        select(TicketLedger).where(
            TicketLedger.id == row_id, TicketLedger.scenic_id == sid
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")

    fields_set = payload.model_fields_set
    if "pay_date" in fields_set:
        row.pay_date = payload.pay_date
    platform_changed = False
    if payload.platform is not None:
        platform_changed = payload.platform != row.platform
    if payload.ticket_product is not None:
        row.ticket_product = payload.ticket_product
    if "repay_date" in fields_set:
        row.repay_date = payload.repay_date
    if "repay_amount" in fields_set:
        row.repay_amount = payload.repay_amount

    # 服务商到账 / 佣金 / 佣金率 / 比例「实际变化」才重算（保证仅改结算金额/回款时不冲掉手工结算）
    received_changed = (
        payload.supplier_received is not None
        and abs(payload.supplier_received - (row.supplier_received or Decimal("0"))) > Decimal("0.005")
    )
    commission_changed = (
        payload.supplier_commission is not None
        and abs(payload.supplier_commission - (row.supplier_commission or Decimal("0"))) > Decimal("0.005")
    )
    commission_rate_changed = (
        payload.commission_rate is not None
        and abs(payload.commission_rate - (row.commission_rate or Decimal("0"))) > Decimal("0.00005")
    )
    rate_hexiao_changed = (
        payload.rate_hexiao is not None
        and abs(payload.rate_hexiao - (row.rate_hexiao or Decimal("0"))) > Decimal("0.00005")
    )
    rate_settle_changed = (
        payload.rate_settle is not None
        and abs(payload.rate_settle - (row.rate_settle or Decimal("0"))) > Decimal("0.00005")
    )
    calc_dirty = any((
        platform_changed,
        received_changed,
        commission_changed,
        commission_rate_changed,
        rate_hexiao_changed,
        rate_settle_changed,
    ))
    calc = effective_daily_json = None
    if calc_dirty:
        calc, effective_daily_json = _effective_ticket_calculation(row, payload)
    if payload.platform is not None:
        row.platform = payload.platform
    # 佣金 override：手工传入佣金金额 → 该值为准；否则 None（佣金随佣金率逐日重算）
    if payload.supplier_received is not None:
        row.supplier_received = payload.supplier_received
    if payload.supplier_commission is not None:
        row.supplier_commission = payload.supplier_commission
    if payload.commission_rate is not None:
        row.commission_rate = payload.commission_rate
    if payload.rate_hexiao is not None:
        row.rate_hexiao = payload.rate_hexiao
    if payload.rate_settle is not None:
        row.rate_settle = payload.rate_settle
    if payload.rate_fee is not None:
        row.rate_fee = payload.rate_fee
    if calc_dirty:
        row.daily_json = effective_daily_json
        row.supplier_commission = calc["supplier_commission"]
        row.publisher_due = calc["publisher_due"]
        row.hexiao_amount = calc["hexiao_amount"]
        row.jinying_amount = calc["jinying_amount"]
        row.service_fee = calc["service_fee"]
    # 结算金额可编辑：显式传入(手工改)则覆盖，服务费=结算−核销
    if payload.jinying_amount is not None:
        row.jinying_amount = payload.jinying_amount
        row.service_fee = row.jinying_amount - row.hexiao_amount
    # 景区核销金额可编辑：显式传入(人工改)则覆盖，服务费=结算−核销
    if payload.hexiao_amount is not None:
        row.hexiao_amount = payload.hexiao_amount
        row.service_fee = row.jinying_amount - row.hexiao_amount

    # 付款金额变化，或核销金额变化 → 影响滚动余额，全景区重算
    balance_dirty = calc_dirty or (payload.hexiao_amount is not None)
    if payload.payment_amount is not None:
        row.payment_amount = payload.payment_amount
        balance_dirty = True
    if payload.co_investment_amount is not None:
        row.co_investment_amount = payload.co_investment_amount

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
    "/{scenic_id}/ticket-ledger/{row_id}",
    response_model=Response[dict],
    summary="删除台账单行(仅该景区)",
)
def delete_row(
    scenic_id: str,
    row_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_delete_guard),
):
    sid = _valid_scenic_id(scenic_id)
    row = db.scalar(
        select(TicketLedger).where(
            TicketLedger.id == row_id, TicketLedger.scenic_id == sid
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")
    # 顺带清理明细源文件
    if row.detail_stored:
        try:
            fp = _detail_dir(sid) / Path(row.detail_stored).name
            if fp.exists():
                fp.unlink()
        except OSError:
            pass
    db.delete(row)
    db.flush()
    # 删除某期后，其后各期滚动余额需重算
    _recompute_running_balance(_load_rows(db, sid))
    db.commit()
    return Response.ok({"deleted": 1}, message="已删除")


@router.delete(
    "/{scenic_id}/ticket-ledger",
    response_model=Response[dict],
    summary="清空某景区门票平台业务台账(仅该景区)",
)
def clear_ledger(
    scenic_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(_delete_guard),
):
    sid = _valid_scenic_id(scenic_id)
    result = db.execute(sa_delete(TicketLedger).where(TicketLedger.scenic_id == sid))
    db.commit()
    return Response.ok({"deleted": result.rowcount or 0}, message="已清空该景区台账")


# --------------------------------------------------------------------------- #
# 6) 导出标准格式业务台账 xlsx
# --------------------------------------------------------------------------- #
@router.get(
    "/{scenic_id}/ticket-ledger/export",
    summary="导出标准格式业务台账(.xlsx，含合计行)",
)
def export_ledger(
    scenic_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(_download_guard),
):
    sid = _valid_scenic_id(scenic_id)
    rows = _load_rows(db, sid)
    if not rows:
        raise HTTPException(status_code=400, detail="该景区暂无台账数据，无法导出")

    export_rows = [
        {
            "platform": r.platform,
            "ticket_product": r.ticket_product,
            "check_date_text": r.check_date_text,
            "hexiao_amount": r.hexiao_amount,
            "pending_writeoff": r.pending_writeoff,
            "payment_amount": r.payment_amount,
            "jinying_amount": r.jinying_amount,
            "service_fee": r.service_fee,
            "repay_date": r.repay_date,
            "repay_amount": r.repay_amount,
        }
        for r in rows
    ]
    data = tl_svc.build_export_workbook(export_rows, title=f"业务台账-{sid}")
    fname = quote(f"业务台账-{sid}.xlsx")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )


# --------------------------------------------------------------------------- #
# 7) 明细源文件预览 / 下载（本次上传或已存台账的对账明细原件）
# --------------------------------------------------------------------------- #
@router.get(
    "/{scenic_id}/ticket-ledger/detail",
    summary="预览/下载对账明细源文件(按 stored 磁盘名，作用域为该景区)",
)
def download_detail(
    scenic_id: str,
    stored: str,
    name: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(_download_guard),
):
    sid = _valid_scenic_id(scenic_id)
    # 路径安全：只取 basename，杜绝 ../ 越权访问其它目录
    safe = Path(stored or "").name
    if not safe:
        raise HTTPException(status_code=400, detail="缺少文件标识")
    path = _detail_dir(sid) / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="明细源文件不存在或已清理")
    return FileResponse(
        str(path),
        filename=name or safe,
        media_type=_XLSX_MIME,
    )


# --------------------------------------------------------------------------- #
# 8) 本期确认函（按期共享；仅业务复核/信息维护可维护）
#    有确认函 → 本期状态=已确认；删除后 → 未确认。同一期各行共享同一确认函。
# --------------------------------------------------------------------------- #
@router.post(
    "/{scenic_id}/ticket-ledger/{row_id}/confirm",
    response_model=Response[TicketLedgerRow],
    summary="上传本期确认函(业务经办/信息维护)→待确认",
)
async def upload_confirm(
    scenic_id: str, row_id: int,
    file: UploadFile = File(..., description="确认函(PDF/图片/Word/Excel)"),
    db: Session = Depends(get_db), _: User = Depends(_update_guard),
):
    sid = _valid_scenic_id(scenic_id)
    row = db.scalar(select(TicketLedger).where(TicketLedger.id == row_id, TicketLedger.scenic_id == sid))
    if not row:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")
    fname = file.filename or "确认函"
    ext = Path(fname).suffix.lower()
    if ext not in _CONFIRM_EXT:
        raise HTTPException(status_code=400, detail="仅支持 PDF/图片/Word/Excel 确认函")
    content = await file.read()
    if len(content) > _CONFIRM_MAX_BYTES:
        raise HTTPException(status_code=400, detail="确认函超过 20MB 上限")
    d = _confirm_dir(sid)
    try:
        d.mkdir(parents=True, exist_ok=True)
        stored = f"{uuid.uuid4().hex}{ext}"
        (d / stored).write_bytes(content)
    except OSError:
        raise HTTPException(status_code=500, detail="确认函保存失败")
    finally:
        del content
    key = _period_key(row)
    old_stored = row.confirm_stored
    for sib in _load_rows(db, sid):
        if _period_key(sib) == key:
            sib.confirm_stored = stored
            sib.confirm_name = fname
            sib.confirmed = False   # 新上传/重传 → 待确认，需业务复核重新确认
    if old_stored and old_stored != stored:
        try:
            old = d / Path(old_stored).name
            if old.exists():
                old.unlink()
        except OSError:
            pass
    db.commit()
    db.refresh(row)
    return Response.ok(_row_out(row), message="确认函已上传，本期状态：待确认")


@router.post(
    "/{scenic_id}/ticket-ledger/{row_id}/confirm/approve",
    response_model=Response[TicketLedgerRow],
    summary="确认本期确认函(仅业务复核/信息维护)→已确认",
)
def approve_confirm(
    scenic_id: str, row_id: int,
    db: Session = Depends(get_db), _: User = Depends(_confirm_guard),
):
    sid = _valid_scenic_id(scenic_id)
    row = db.scalar(select(TicketLedger).where(TicketLedger.id == row_id, TicketLedger.scenic_id == sid))
    if not row:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")
    if not row.confirm_stored:
        raise HTTPException(status_code=400, detail="本期尚未上传确认函，无法确认")
    key = _period_key(row)
    for sib in _load_rows(db, sid):
        if _period_key(sib) == key:
            sib.confirmed = True
    db.commit()
    db.refresh(row)
    return Response.ok(_row_out(row), message="本期状态：已确认")


@router.get("/{scenic_id}/ticket-ledger/confirm", summary="查看/下载本期确认函(台账下载角色)")
def download_confirm(
    scenic_id: str, stored: str, name: str = "",
    db: Session = Depends(get_db), _: User = Depends(_download_guard),
):
    sid = _valid_scenic_id(scenic_id)
    safe = Path(stored or "").name
    if not safe:
        raise HTTPException(status_code=400, detail="缺少文件标识")
    path = _confirm_dir(sid) / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="确认函不存在或已删除")
    mt = mimetypes.guess_type(name or safe)[0] or "application/octet-stream"
    return FileResponse(str(path), filename=name or safe, media_type=mt)


@router.delete(
    "/{scenic_id}/ticket-ledger/{row_id}/confirm",
    response_model=Response[dict],
    summary="删除本期确认函(业务经办/信息维护)→未确认",
)
def delete_confirm(
    scenic_id: str, row_id: int,
    db: Session = Depends(get_db), _: User = Depends(_delete_guard),
):
    sid = _valid_scenic_id(scenic_id)
    row = db.scalar(select(TicketLedger).where(TicketLedger.id == row_id, TicketLedger.scenic_id == sid))
    if not row:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")
    key = _period_key(row)
    stored = row.confirm_stored
    for sib in _load_rows(db, sid):
        if _period_key(sib) == key:
            sib.confirm_stored = ""
            sib.confirm_name = ""
            sib.confirmed = False
    if stored:
        try:
            fp = _confirm_dir(sid) / Path(stored).name
            if fp.exists():
                fp.unlink()
        except OSError:
            pass
    db.commit()
    return Response.ok({"deleted": 1}, message="确认函已删除，本期状态：未确认")
