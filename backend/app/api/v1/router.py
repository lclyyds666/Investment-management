"""v1 版本路由汇总。"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, channel, contract, customer, health, invoice, knowledge, operation, user,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["系统"])
api_router.include_router(auth.router, tags=["认证"])
api_router.include_router(user.router, prefix="/users", tags=["用户与组织"])
api_router.include_router(contract.router, prefix="/contracts", tags=["合同管理"])
api_router.include_router(operation.router, prefix="/operation", tags=["经营数据"])
api_router.include_router(customer.router, prefix="/customers", tags=["客户档案"])
api_router.include_router(channel.router, prefix="/channels", tags=["渠道集成"])
api_router.include_router(invoice.router, prefix="/invoices", tags=["发票管理"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["法规知识库"])
