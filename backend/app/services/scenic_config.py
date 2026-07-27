"""景区核销台账默认配置读取与维护服务。"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Literal

from sqlalchemy.orm import Session

from app.models.scenic_config import ScenicConfig

DEFAULT_TICKET_PRODUCT = "水上世界/童话世界/海洋王国"
DEFAULT_HOTEL_NAME = "郑和海洋酒店、宝船酒店、水上酒店、长颈鹿酒店"
DEFAULT_RATE_HEXIAO = Decimal("0.9000")
DEFAULT_RATE_SETTLE = Decimal("0.9400")
DEFAULT_COMMISSION_RATE = Decimal("0.0600")
DEFAULT_HOTEL_FEE_ALGO = 1
DEFAULT_FEE_PER_NIGHT = Decimal("44.00")


@dataclass(frozen=True)
class EffectiveScenicConfig:
    scenic_id: str
    scenic_name: str
    default_ticket_product: str
    default_hotel_name: str
    rate_hexiao: Decimal
    rate_settle: Decimal
    commission_rate: Decimal
    hotel_fee_algo: int
    fee_per_night: Decimal
    enabled: bool
    configured: bool
    source: Literal["database", "fallback"]
    created_at: datetime | None = None
    updated_at: datetime | None = None


def get_effective_scenic_config(db: Session, scenic_id: str) -> EffectiveScenicConfig:
    """读取景区配置；缺少配置行时返回与当前生产一致的全局默认值。"""
    row = db.get(ScenicConfig, scenic_id)
    if row is None:
        return EffectiveScenicConfig(
            scenic_id=scenic_id,
            scenic_name="",
            default_ticket_product=DEFAULT_TICKET_PRODUCT,
            default_hotel_name=DEFAULT_HOTEL_NAME,
            rate_hexiao=DEFAULT_RATE_HEXIAO,
            rate_settle=DEFAULT_RATE_SETTLE,
            commission_rate=DEFAULT_COMMISSION_RATE,
            hotel_fee_algo=DEFAULT_HOTEL_FEE_ALGO,
            fee_per_night=DEFAULT_FEE_PER_NIGHT,
            enabled=True,
            configured=False,
            source="fallback",
        )
    return EffectiveScenicConfig(
        scenic_id=row.scenic_id,
        scenic_name=row.scenic_name,
        default_ticket_product=row.default_ticket_product,
        default_hotel_name=row.default_hotel_name,
        rate_hexiao=row.rate_hexiao,
        rate_settle=row.rate_settle,
        commission_rate=row.commission_rate,
        hotel_fee_algo=row.hotel_fee_algo,
        fee_per_night=row.fee_per_night,
        enabled=row.enabled,
        configured=True,
        source="database",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def upsert_scenic_config(
    db: Session, scenic_id: str, values: Mapping[str, Any]
) -> ScenicConfig:
    """创建或完整更新一条景区配置；事务提交由调用端负责。"""
    row = db.get(ScenicConfig, scenic_id)
    if row is None:
        row = ScenicConfig(scenic_id=scenic_id)
        db.add(row)
    for field, value in values.items():
        setattr(row, field, value)
    return row
