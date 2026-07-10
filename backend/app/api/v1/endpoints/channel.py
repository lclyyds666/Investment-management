"""多渠道数据集成端点。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.enums import DIRECTOR_ROLES
from app.db.session import get_db
from app.models.channel import Channel, ChannelData
from app.models.user import User
from app.schemas.channel import (
    ChannelCreate, ChannelDataIn, ChannelDataOut, ChannelOut, ChannelUpdate,
)
from app.schemas.common import Response
from app.services.channel_etl import sync_channel_to_operation

router = APIRouter()


@router.get("", response_model=Response[list[ChannelOut]], summary="渠道平台列表")
def list_channels(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(Channel).order_by(Channel.sort_order, Channel.id)).all()
    return Response.ok([ChannelOut.model_validate(r) for r in rows])


@router.post(
    "", response_model=Response[ChannelOut], summary="新增渠道平台",
    dependencies=[Depends(require_roles(*DIRECTOR_ROLES))],
)
def create_channel(payload: ChannelCreate, db: Session = Depends(get_db)):
    ch = Channel(**payload.model_dump())
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return Response.ok(ChannelOut.model_validate(ch))


@router.put(
    "/{cid}", response_model=Response[ChannelOut], summary="修改渠道平台",
    dependencies=[Depends(require_roles(*DIRECTOR_ROLES))],
)
def update_channel(cid: int, payload: ChannelUpdate, db: Session = Depends(get_db)):
    ch = db.get(Channel, cid)
    if not ch:
        raise HTTPException(status_code=404, detail="渠道不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ch, field, value)
    db.commit()
    db.refresh(ch)
    return Response.ok(ChannelOut.model_validate(ch))


@router.delete(
    "/{cid}", response_model=Response[dict], summary="删除渠道平台",
    dependencies=[Depends(require_roles(*DIRECTOR_ROLES))],
)
def delete_channel(cid: int, db: Session = Depends(get_db)):
    ch = db.get(Channel, cid)
    if not ch:
        raise HTTPException(status_code=404, detail="渠道不存在")
    db.delete(ch)
    db.commit()
    return Response.ok({"id": cid})


@router.get("/{cid}/data", response_model=Response[ChannelDataOut], summary="渠道回传数据")
def get_channel_data(cid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    ch = db.get(Channel, cid)
    if not ch:
        raise HTTPException(status_code=404, detail="渠道不存在")
    data = db.scalar(select(ChannelData).where(ChannelData.channel_id == cid))
    if not data:
        return Response.ok(ChannelDataOut(channel_id=cid, columns=[], rows=[]))
    return Response.ok(ChannelDataOut.model_validate(data))


@router.put("/{cid}/data", response_model=Response[ChannelDataOut], summary="回传/导入渠道数据")
def import_channel_data(
    cid: int,
    payload: ChannelDataIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """导入外部导出的表格数据（列 + 行 + 列映射），覆盖式保存；若配置了映射，
    则按映射把数据汇入经营数据表（biz_operation_data），联动首页与大屏图表。"""
    ch = db.get(Channel, cid)
    if not ch:
        raise HTTPException(status_code=404, detail="渠道不存在")
    data = db.scalar(select(ChannelData).where(ChannelData.channel_id == cid))
    if not data:
        data = ChannelData(channel_id=cid)
        db.add(data)
    data.columns = payload.columns
    data.rows = payload.rows
    mapping = payload.mapping.model_dump() if payload.mapping else None
    data.mapping = mapping
    db.commit()
    db.refresh(data)

    # 按映射汇入经营表（覆盖式、幂等）；无映射时返回未同步说明
    sync = sync_channel_to_operation(db, ch, data.columns or [], data.rows or [], mapping)

    out = ChannelDataOut.model_validate(data)
    out.sync = sync
    return Response.ok(out)
