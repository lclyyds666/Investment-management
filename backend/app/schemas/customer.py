"""客户档案 schema。"""
from typing import Optional

from pydantic import BaseModel, ConfigDict


class FileRef(BaseModel):
    name: str
    url: str = ""


class CustomerBase(BaseModel):
    name: str
    social_credit_code: str = ""
    address: str = ""
    contact: str = ""
    phone: str = ""
    admission_files: Optional[list[FileRef]] = None
    remark: str = ""


class CustomerCreate(CustomerBase):
    customer_code: str


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    social_credit_code: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    admission_files: Optional[list[FileRef]] = None
    remark: Optional[str] = None


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_code: str
