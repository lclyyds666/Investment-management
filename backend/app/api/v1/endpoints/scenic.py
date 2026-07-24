"""文旅业务·景区核销数据台账端点（严格按 scenic_id 数据隔离）。

数据作用域铁律：
- scenic_id **一律取自 URL 路径**，不信任任何请求体传入的 scenic_id；
- 查询/删除强制 `WHERE scenic_id = :sid`；上传时每一行落库的 scenic_id 强制写为路径值；
- 任何接口都不会返回非当前 scenic_id 的数据。
"""
import io
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.hotel_ledger import HotelLedger
from app.models.scenic import ScenicLedger
from app.models.ticket_ledger import TicketLedger
from app.models.user import User
from app.schemas.common import Response
from app.schemas.scenic import ScenicLedgerOut, ScenicLedgerRow, ScenicUploadResult

router = APIRouter()

_XLSX_EXT = {".xlsx", ".xls"}
_MAX_BYTES = 20 * 1024 * 1024  # ≤ 20MB


def _valid_scenic_id(scenic_id: str) -> str:
    """校验并归一 scenic_id（作用域键）。为空/超长直接拒绝。"""
    sid = (scenic_id or "").strip()
    if not sid or len(sid) > 64:
        raise HTTPException(status_code=400, detail="景区标识(scenic_id)非法")
    return sid


def _cell_to_jsonable(v):
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()[:19].replace("T", " ")
    return v


def _parse_excel(content: bytes) -> tuple[list[str], list[dict]]:
    """解析 Excel：首个非空行为表头，其后为数据行。返回 (columns, rows)。"""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)

    # 表头：第一行有内容的行
    headers: list[str] = []
    for raw in rows_iter:
        vals = [(_cell_to_jsonable(c)) for c in raw]
        if any(str(v).strip() for v in vals):
            headers = [str(v).strip() or f"列{i+1}" for i, v in enumerate(vals)]
            break
    if not headers:
        return [], []

    # 去除末尾全空列
    while headers and not headers[-1]:
        headers.pop()
    ncol = len(headers)

    data_rows: list[dict] = []
    for raw in rows_iter:
        vals = [_cell_to_jsonable(c) for c in raw][:ncol]
        if not any(str(v).strip() for v in vals):
            continue  # 跳过空行
        vals += [""] * (ncol - len(vals))
        data_rows.append({headers[i]: vals[i] for i in range(ncol)})
    return headers, data_rows


def _columns_of(rows: list[dict]) -> list[str]:
    """按首次出现顺序取并集列名。"""
    cols: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    return cols


@router.get(
    "/{scenic_id}/ledger",
    response_model=Response[ScenicLedgerOut],
    summary="查询某景区核销台账（仅该景区数据）",
)
def get_ledger(
    scenic_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    # 数据隔离：强制 WHERE scenic_id = :sid
    records = db.scalars(
        select(ScenicLedger)
        .where(ScenicLedger.scenic_id == sid)
        .order_by(ScenicLedger.row_no.asc(), ScenicLedger.id.asc())
    ).all()
    rows = [ScenicLedgerRow.model_validate(r) for r in records]
    columns = _columns_of([r.data for r in records])
    return Response.ok(ScenicLedgerOut(scenic_id=sid, columns=columns, rows=rows, total=len(rows)))


@router.post(
    "/{scenic_id}/ledger",
    response_model=Response[ScenicUploadResult],
    summary="上传 Excel 核销台账（数据强制归属该景区）",
)
async def upload_ledger(
    scenic_id: str,
    file: UploadFile = File(..., description="核销数据 Excel(.xlsx/.xls)，≤20MB"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    fname = file.filename or "台账.xlsx"
    if Path(fname).suffix.lower() not in _XLSX_EXT:
        raise HTTPException(status_code=400, detail="仅支持 Excel 文件(.xlsx/.xls)")
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 20MB 上限")
    try:
        columns, rows = _parse_excel(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Excel 解析失败：{exc}")
    if not rows:
        raise HTTPException(status_code=400, detail="未解析到有效数据行")

    # 追加式入库；scenic_id 强制取路径值，忽略数据内任何 scenic 字段
    # 起始 row_no 接续当前该景区最大行序，保证多次上传顺序稳定
    max_no = db.scalar(
        select(ScenicLedger.row_no)
        .where(ScenicLedger.scenic_id == sid)
        .order_by(ScenicLedger.row_no.desc())
        .limit(1)
    ) or 0
    for i, r in enumerate(rows, start=1):
        db.add(ScenicLedger(
            scenic_id=sid,                 # ← 铁律：作用域键来自路径
            row_no=max_no + i,
            data=r,
            source_file=fname,
            uploaded_by=current_user.id,
        ))
    db.commit()
    return Response.ok(
        ScenicUploadResult(scenic_id=sid, inserted=len(rows), columns=columns, source_file=fname),
        message=f"已导入 {len(rows)} 行核销数据",
    )


@router.delete(
    "/{scenic_id}/ledger",
    response_model=Response[dict],
    summary="清空某景区核销台账（仅清该景区）",
)
def clear_ledger(
    scenic_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    sid = _valid_scenic_id(scenic_id)
    # 数据隔离：只删该景区，绝不波及其他景区
    result = db.execute(sa_delete(ScenicLedger).where(ScenicLedger.scenic_id == sid))
    db.commit()
    return Response.ok({"scenic_id": sid, "deleted": result.rowcount or 0}, message="已清空该景区台账")


@router.get(
    "/{scenic_id}/metrics",
    response_model=Response[dict],
    summary="景区经营数据卡片(销售额/核销数/核销率)——每景区独立",
)
def get_metrics(scenic_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """销售额 = 门票+酒店核销台账结算金额之和；核销数 = 两台账订单号数量之和(order_count)；
    核销率 = 两台账「订单实收/结算价/结算金额为正数」订单数之和 ÷ 核销数 × 100%。"""
    sid = _valid_scenic_id(scenic_id)

    def _sums(model):
        r = db.execute(
            select(
                func.coalesce(func.sum(model.jinying_amount), 0),
                func.coalesce(func.sum(model.order_count), 0),
                func.coalesce(func.sum(model.positive_count), 0),
            ).where(model.scenic_id == sid)
        ).one()
        return r[0] or 0, int(r[1] or 0), int(r[2] or 0)

    t_sales, t_cnt, t_pos = _sums(TicketLedger)
    h_sales, h_cnt, h_pos = _sums(HotelLedger)
    sales = float(t_sales) + float(h_sales)
    writeoff = t_cnt + h_cnt
    positive = t_pos + h_pos
    rate = round(positive / writeoff * 100, 2) if writeoff else 0.0
    return Response.ok({
        "scenic_id": sid,
        "sales": sales,               # 销售额(元)
        "writeoff_count": writeoff,   # 核销数
        "positive_count": positive,
        "rate": rate,                 # 核销率(%)
    })
