"""多渠道数据集成 schema。"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.core.enums import CHANNEL_CATEGORY_LABELS


class ChannelBase(BaseModel):
    name: str
    category: str = "other"
    url: str = ""
    account: str = ""
    password: str = ""
    logo: str = "🔗"
    description: str = ""
    sort_order: int = 0


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    account: Optional[str] = None
    password: Optional[str] = None
    logo: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class ChannelOut(ChannelBase):
    model_config = ConfigDict(from_attributes=True)

    id: int

    @computed_field
    @property
    def category_label(self) -> str:
        return CHANNEL_CATEGORY_LABELS.get(self.category, self.category)


class ChannelDataIn(BaseModel):
    columns: list[str] = []
    rows: list[list] = []


class ChannelDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_id: int
    columns: Optional[list] = None
    rows: Optional[list] = None
