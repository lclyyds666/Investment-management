"""景区配置的唯一默认值解析入口。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scenic_config import ScenicConfig


SYSTEM_TICKET_PRODUCT = "水上世界/童话世界/海洋王国"
SYSTEM_RATE_HEXIAO = Decimal("0.90")
SYSTEM_RATE_SETTLE = Decimal("0.94")
SYSTEM_COMMISSION_RATE = Decimal("0.06")

SCENIC_SEEDS = (
    ("quancheng-ouleb", "泉城欧乐堡", 10, SYSTEM_TICKET_PRODUCT, "0.90", "0.94", "0.06", None),
    ("quanzhou-ouleb", "泉州欧乐堡", 20, SYSTEM_TICKET_PRODUCT, "0.90", "0.94", "0.06", None),
    ("fuzhou-ouleb", "福州欧乐堡", 30, SYSTEM_TICKET_PRODUCT, "0.91", "0.95", "0.08", None),
    ("zunyi-zoo", "遵义动物园", 40, "遵义动物园", "0.84", "0.87", "0", "0"),
    ("nanyang-wildlife", "南阳森林野生动物世界", 50, "南阳森林野生动物世界", "0.80", "0.85", "0", "0"),
    ("guanquelou", "鹳雀楼", 60, SYSTEM_TICKET_PRODUCT, "0.90", "0.94", "0.06", None),
)


@dataclass(frozen=True)
class EffectiveScenicConfig:
    scenic_id: str
    scenic_name: str
    sort_order: int
    default_ticket_product: str
    ticket_rate_hexiao: Decimal
    ticket_rate_settle: Decimal
    ticket_commission_rate: Decimal
    ticket_default_commission: Decimal | None
    configured: bool
    updated_by: int | None = None
    updated_at: datetime | None = None


def _seed_config(scenic_id: str) -> EffectiveScenicConfig:
    seed = next((item for item in SCENIC_SEEDS if item[0] == scenic_id), None)
    if seed is None:
        return EffectiveScenicConfig(
            scenic_id=scenic_id,
            scenic_name=scenic_id,
            sort_order=999,
            default_ticket_product=SYSTEM_TICKET_PRODUCT,
            ticket_rate_hexiao=SYSTEM_RATE_HEXIAO,
            ticket_rate_settle=SYSTEM_RATE_SETTLE,
            ticket_commission_rate=SYSTEM_COMMISSION_RATE,
            ticket_default_commission=None,
            configured=False,
        )
    sid, name, order, product, hexiao, settle, commission_rate, commission = seed
    return EffectiveScenicConfig(
        scenic_id=sid,
        scenic_name=name,
        sort_order=order,
        default_ticket_product=product,
        ticket_rate_hexiao=Decimal(hexiao),
        ticket_rate_settle=Decimal(settle),
        ticket_commission_rate=Decimal(commission_rate),
        ticket_default_commission=Decimal(commission) if commission is not None else None,
        configured=False,
    )


def _from_model(row: ScenicConfig) -> EffectiveScenicConfig:
    return EffectiveScenicConfig(
        scenic_id=row.scenic_id,
        scenic_name=row.scenic_name,
        sort_order=row.sort_order,
        default_ticket_product=row.default_ticket_product,
        ticket_rate_hexiao=row.ticket_rate_hexiao,
        ticket_rate_settle=row.ticket_rate_settle,
        ticket_commission_rate=row.ticket_commission_rate,
        ticket_default_commission=row.ticket_default_commission,
        configured=True,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


def get_effective_config(db: Session | None, scenic_id: str) -> EffectiveScenicConfig:
    """读取持久化配置；缺表/缺行时使用已知景区种子或系统兜底。"""
    if db is not None:
        try:
            row = db.get(ScenicConfig, scenic_id)
            if row is not None:
                return _from_model(row)
        except Exception:  # noqa: BLE001 - 迁移未执行时仍允许只读解析兜底
            pass
    return _seed_config(scenic_id)


def list_effective_configs(db: Session) -> list[EffectiveScenicConfig]:
    rows = db.scalars(select(ScenicConfig).order_by(ScenicConfig.sort_order, ScenicConfig.scenic_id)).all()
    by_id = {row.scenic_id: _from_model(row) for row in rows}
    for seed in SCENIC_SEEDS:
        by_id.setdefault(seed[0], _seed_config(seed[0]))
    return sorted(by_id.values(), key=lambda item: (item.sort_order, item.scenic_id))
