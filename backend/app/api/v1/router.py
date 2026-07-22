"""v1 版本路由汇总。"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    approval, approval_stats, audit, auth, channel, contract, customer, health, hotel_ledger,
    invoice, knowledge, operation, scenic, ticket_ledger, user,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["系统"])
api_router.include_router(auth.router, tags=["认证"])
api_router.include_router(user.router, prefix="/users", tags=["用户与组织"])
api_router.include_router(contract.router, prefix="/contracts", tags=["合同管理"])
api_router.include_router(approval.router, prefix="/approval-forms", tags=["业务审批"])
api_router.include_router(approval_stats.router, prefix="/approval", tags=["审批角标"])
api_router.include_router(audit.router, tags=["操作审计"])
api_router.include_router(operation.router, prefix="/operation", tags=["经营数据"])
api_router.include_router(customer.router, prefix="/customers", tags=["客户档案"])
api_router.include_router(channel.router, prefix="/channels", tags=["渠道集成"])
api_router.include_router(invoice.router, prefix="/invoices", tags=["发票管理"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["法规知识库"])
api_router.include_router(scenic.router, prefix="/scenic-spots", tags=["文旅业务"])
api_router.include_router(ticket_ledger.router, prefix="/scenic-spots", tags=["文旅业务·门票台账"])
api_router.include_router(hotel_ledger.router, prefix="/scenic-spots", tags=["文旅业务·酒店台账"])
