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
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.ticket_ledger import TicketLedger
from app.models.user import User
from app.schemas.common import Response
from app.schemas.ticket_ledger import (
    ParsedFile,
    ParseResult,
    TicketLedgerOut,
    TicketLedgerRow,
    TicketLedgerSaveIn,
    TicketLedgerTotals,
    TicketLedgerUpdateIn,
)
from app.services import ticket_ledger as tl_svc

router = APIRouter()

_XLSX_EXT = {".xlsx", ".xls"}
_MAX_BYTES = 30 * 1024 * 1024  # ≤ 30MB（明细可能上万行）
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 解析并发闸：小内存机(1.6GB)上，大文件解析(万行明细)峰值资源高。
# 限制同一时刻只跑 1 个解析，重叠上传排队而非叠加 → 防 OOM 僵死。
_PARSE_SEMAPHORE = asyncio.Semaphore(1)


def _valid_scenic_id(scenic_id: str) -> str:
    sid = (scenic_id or "").strip()
    if not sid or len(sid) > 64:
        raise HTTPException(status_code=400, detail="景区标识(scenic_id)非法")
    return sid


def _row_out(r: TicketLedger) -> TicketLedgerRow:
    return TicketLedgerRow.model_validate(r)


def _totals(rows: list[TicketLedger]) -> TicketLedgerTotals:
    def s(attr):
        return sum((getattr(x, attr) or Decimal("0") for x in rows), Decimal("0"))

    return TicketLedgerTotals(
        hexiao_amount=s("hexiao_amount"),
        jinying_amount=s("jinying_amount"),
        service_fee=s("service_fee"),
        publisher_due=s("publisher_due"),
        repay_amount=s("repay_amount"),
    )


def _load_rows(db: Session, sid: str) -> list[TicketLedger]:
    return db.scalars(
        select(TicketLedger)
        .where(TicketLedger.scenic_id == sid)
        .order_by(TicketLedger.row_no.asc(), TicketLedger.id.asc())
    ).all()


# --------------------------------------------------------------------------- #
# 1) 批量上传 → 解析（不落库）
# --------------------------------------------------------------------------- #
@router.post(
    "/{scenic_id}/ticket-ledger/parse",
    response_model=Response[ParseResult],
    summary="批量上传对账明细并解析(算服务商到账+周期，不落库)",
)
async def parse_files(
    scenic_id: str,
    files: list[UploadFile] = File(..., description="对账明细 Excel(.xlsx/.xls)，可多选"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    parsed: list[ParsedFile] = []
    warnings: list[str] = []
    failed = 0

    for f in files:
        fname = f.filename or "对账明细.xlsx"
        if Path(fname).suffix.lower() not in _XLSX_EXT:
            failed += 1
            warnings.append(f"{fname}：仅支持 Excel(.xlsx/.xls)，已跳过")
            continue
        content = await f.read()
        if len(content) > _MAX_BYTES:
            failed += 1
            warnings.append(f"{fname}：超过 30MB 上限，已跳过")
            continue
        try:
            # 并发闸 + 线程池：CPU/内存密集的 openpyxl 解析不阻塞事件循环，
            # 且同一时刻只跑一个解析，避免重叠上传在小内存机上叠加 OOM。
            async with _PARSE_SEMAPHORE:
                info = await run_in_threadpool(
                    tl_svc.parse_reconciliation, content, filename=fname
                )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            warnings.append(f"{fname}：解析失败（{exc}）")
            continue
        finally:
            # 尽快释放大文件内存，降低小内存机 OOM 风险
            del content
        if info["order_count"] == 0:
            warnings.append(f"{fname}：未解析到有效核销明细，请确认文件内容")
        parsed.append(ParsedFile(
            source_file=fname,
            supplier_received=info["supplier_received"],
            order_count=info["order_count"],
            period_text=info["period_text"],
            check_date_text=info["check_date_text"],
            period_start=info["period_start"],
            period_end=info["period_end"],
            sheets=info["sheets"],
            suggested_publisher_due=info["supplier_received"],  # 建议值=服务商到账，用户可改
        ))

    # 按周期起始排序，便于台账时间顺序
    parsed.sort(key=lambda p: (p.period_start or date.max))
    return Response.ok(
        ParseResult(
            scenic_id=sid,
            files=parsed,
            succeeded=len(parsed),
            failed=failed,
            warnings=warnings,
        ),
        message=f"解析完成：成功 {len(parsed)} 个，失败 {failed} 个",
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
    _: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)

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
        calc = tl_svc.compute_row(r.publisher_due, r.rate_hexiao, r.rate_fee)
        db.add(TicketLedger(
            scenic_id=sid,                       # ← 铁律：作用域键来自路径
            row_no=base_no + i,
            pay_date=r.pay_date,
            platform=r.platform or "",
            ticket_product=r.ticket_product or tl_svc.DEFAULT_TICKET_PRODUCT,
            check_date_text=r.check_date_text or "",
            period_text=r.period_text or "",
            period_start=r.period_start,
            period_end=r.period_end,
            supplier_received=r.supplier_received or Decimal("0"),
            publisher_due=calc["publisher_due"],
            hexiao_amount=calc["hexiao_amount"],
            jinying_amount=calc["jinying_amount"],
            service_fee=calc["service_fee"],
            rate_hexiao=r.rate_hexiao,
            rate_fee=r.rate_fee,
            order_count=r.order_count or 0,
            repay_date=r.repay_date,
            repay_amount=r.repay_amount,
            source_file=r.source_file or "",
            uploaded_by=current_user.id,
        ))
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
    _: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    row = db.scalar(
        select(TicketLedger).where(
            TicketLedger.id == row_id, TicketLedger.scenic_id == sid
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")

    if payload.pay_date is not None:
        row.pay_date = payload.pay_date
    if payload.platform is not None:
        row.platform = payload.platform
    if payload.ticket_product is not None:
        row.ticket_product = payload.ticket_product
    if payload.repay_date is not None:
        row.repay_date = payload.repay_date
    if payload.repay_amount is not None:
        row.repay_amount = payload.repay_amount

    # B 或比例变化 → 重算三列
    if payload.rate_hexiao is not None:
        row.rate_hexiao = payload.rate_hexiao
    if payload.rate_fee is not None:
        row.rate_fee = payload.rate_fee
    if payload.publisher_due is not None:
        row.publisher_due = payload.publisher_due
    if (
        payload.publisher_due is not None
        or payload.rate_hexiao is not None
        or payload.rate_fee is not None
    ):
        calc = tl_svc.compute_row(row.publisher_due, row.rate_hexiao, row.rate_fee)
        row.publisher_due = calc["publisher_due"]
        row.hexiao_amount = calc["hexiao_amount"]
        row.jinying_amount = calc["jinying_amount"]
        row.service_fee = calc["service_fee"]

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
    _: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    result = db.execute(
        sa_delete(TicketLedger).where(
            TicketLedger.id == row_id, TicketLedger.scenic_id == sid
        )
    )
    db.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="台账行不存在或不属于该景区")
    return Response.ok({"deleted": result.rowcount}, message="已删除")


@router.delete(
    "/{scenic_id}/ticket-ledger",
    response_model=Response[dict],
    summary="清空某景区门票平台业务台账(仅该景区)",
)
def clear_ledger(
    scenic_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
    _: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    rows = _load_rows(db, sid)
    if not rows:
        raise HTTPException(status_code=400, detail="该景区暂无台账数据，无法导出")

    export_rows = [
        {
            "pay_date": r.pay_date,
            "platform": r.platform,
            "ticket_product": r.ticket_product,
            "check_date_text": r.check_date_text,
            "hexiao_amount": r.hexiao_amount,
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
