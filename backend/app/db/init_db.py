"""初始化数据库：建表并写入种子数据（7 级组织角色 + 电子签名）。

可直接运行：python -m app.db.init_db
（对已存在的账号/数据不重复写入。）
"""
import base64
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import InvoiceStatus, Role
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
# 导入全部模型，确保 create_all 能发现并建表
from app.models.approval import Approval  # noqa: F401
from app.models.approval_form import ApprovalForm, ApprovalFormAction  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401 确保 create_all 建表
from app.models.channel import Channel, ChannelData
from app.models.contract import Contract  # noqa: F401
from app.models.customer import Customer
from app.models.financial import FinanceConfig, FinancialMetrics  # noqa: F401
from app.models.invoice import Invoice
from app.models.knowledge import KnowledgeDoc  # noqa: F401 确保 create_all 建表
from app.models.operation import OperationData
from app.models.project import ProjectMetrics  # noqa: F401
from app.models.research import CustomerMaterial, CustomerResearch  # noqa: F401
from app.models.scenic import ScenicLedger  # noqa: F401
from app.models.ticket_ledger import TicketLedger  # noqa: F401 确保 create_all 建表
from app.models.user import User


def mock_signature(name: str) -> str:
    """生成一枚 Mock 电子签名（红色手写体姓名的 SVG，base64 data-URI，稳定可渲染）。"""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="60">'
        '<text x="10" y="42" font-family="KaiTi,STKaiti,cursive,serif" '
        'font-size="34" fill="#c0392b" font-style="italic">' + name + '</text></svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


# 8 个默认账号（admin 超管 + 7 级角色各一），密码统一 123456。
SEED_USERS = [
    {"username": "admin",  "full_name": "信息维护",   "role": Role.INFO_MAINTAINER,   "department": "信息中心",   "is_superuser": True},
    {"username": "op",     "full_name": "张经办",     "role": Role.BUSINESS_HANDLER,  "department": "业务部",     "is_superuser": False},
    {"username": "review", "full_name": "李复核",     "role": Role.BUSINESS_REVIEWER, "department": "业务部",     "is_superuser": False},
    {"username": "risk",   "full_name": "王风控",     "role": Role.RISK_AUDITOR,      "department": "风控合规部", "is_superuser": False},
    {"username": "fin",    "full_name": "赵财办",     "role": Role.FINANCE_HANDLER,   "department": "财务部",     "is_superuser": False},
    {"username": "finr",   "full_name": "孙财复",     "role": Role.FINANCE_REVIEWER,  "department": "财务部",     "is_superuser": False},
    {"username": "scm",    "full_name": "周供管",     "role": Role.SCM_DIRECTOR,      "department": "供管公司",   "is_superuser": False},
    {"username": "inv",    "full_name": "吴投资",     "role": Role.INVEST_DIRECTOR,   "department": "投资公司",   "is_superuser": False},
    {"username": "legal",  "full_name": "陈法顾",     "role": Role.LEGAL_COUNSEL,     "department": "法务部",     "is_superuser": False},
]

SEED_LINES = ["图书发行", "数字出版", "物流仓储"]


def seed_users(db: Session) -> None:
    for item in SEED_USERS:
        exists = db.scalar(select(User).where(User.username == item["username"]))
        if exists:
            # 补齐缺失的签名（便于旧库升级后仍有签章可用）
            if not exists.signature:
                exists.signature = mock_signature(item["full_name"])
            continue
        db.add(
            User(
                username=item["username"],
                full_name=item["full_name"],
                role=item["role"],
                department=item["department"],
                is_superuser=item["is_superuser"],
                signature=mock_signature(item["full_name"]),
                hashed_password=hash_password("123456"),
            )
        )
    db.commit()


def seed_operation(db: Session) -> None:
    if db.scalar(select(OperationData).limit(1)):
        return
    base = {"图书发行": 1200000, "数字出版": 800000, "物流仓储": 500000}
    for month in range(1, 7):
        for line in SEED_LINES:
            revenue = Decimal(base[line]) * Decimal(1 + month * 0.05)
            cost = revenue * Decimal("0.7")
            db.add(
                OperationData(
                    year=2026,
                    month=month,
                    business_line=line,
                    revenue=revenue,
                    cost=cost,
                    profit=revenue - cost,
                    order_count=100 + month * 10,
                )
            )
    db.commit()


def seed_customers(db: Session) -> None:
    if db.scalar(select(Customer).limit(1)):
        return
    demo = [
        {"customer_code": "KH-001", "name": "济南新华书店有限公司", "address": "济南市市中区经十路", "contact": "刘经理", "phone": "0531-88886666"},
        {"customer_code": "KH-002", "name": "青岛出版发行集团", "address": "青岛市市南区香港中路", "contact": "陈主任", "phone": "0532-85881234"},
        {"customer_code": "KH-003", "name": "齐鲁印刷有限公司", "address": "济南市历城区工业北路", "contact": "王厂长", "phone": "0531-66668888"},
    ]
    for d in demo:
        db.add(Customer(**d, admission_files=[{"name": "营业执照.pdf", "url": ""}], remark="演示客户"))
    db.commit()


def seed_channels(db: Session) -> None:
    if db.scalar(select(Channel).limit(1)):
        return
    demo = [
        {"name": "携程商旅", "category": "hotel", "url": "https://www.ctrip.com", "account": "sdcbgl_ctrip", "password": "Ctrip@2026", "logo": "🏨", "description": "酒店与差旅数据平台", "sort_order": 1},
        {"name": "美团到综", "category": "ticket", "url": "https://www.meituan.com", "account": "sdcbgl_mt", "password": "Meituan@2026", "logo": "🎫", "description": "景区门票与本地生活", "sort_order": 2},
        {"name": "去哪儿网", "category": "ota", "url": "https://www.qunar.com", "account": "sdcbgl_qunar", "password": "Qunar@2026", "logo": "✈️", "description": "综合 OTA 平台", "sort_order": 3},
        {"name": "同程旅行", "category": "ticket", "url": "https://www.ly.com", "account": "sdcbgl_ly", "password": "Ly@2026", "logo": "🎟️", "description": "景区门票数据", "sort_order": 4},
    ]
    for d in demo:
        db.add(Channel(**d))
    db.commit()


def seed_channel_data(db: Session) -> None:
    """为示例渠道「携程商旅」写入一份带列映射的回传数据，并汇入经营表，
    开箱即可在首页/大屏看到"渠道 → 经营看板"的真实联动效果。"""
    ch = db.scalar(select(Channel).where(Channel.name == "携程商旅"))
    if not ch:
        return
    existing = db.scalar(select(ChannelData).where(ChannelData.channel_id == ch.id))
    if existing and existing.mapping:
        return  # 已有真实配置（含映射）则尊重用户数据，不覆盖

    columns = ["日期", "订单数", "核销数", "交易金额(元)", "成本(元)"]
    rows = [
        ["2026-01-15", "320", "300", "960000", "610000"],
        ["2026-02-15", "300", "285", "900000", "575000"],
        ["2026-03-15", "360", "340", "1080000", "690000"],
        ["2026-04-15", "390", "370", "1170000", "748000"],
        ["2026-05-15", "420", "400", "1260000", "806000"],
        ["2026-06-15", "450", "430", "1350000", "864000"],
    ]
    mapping = {
        "date_col": "日期",
        "revenue_col": "交易金额(元)",
        "cost_col": "成本(元)",
        "order_col": "订单数",
        "business_line": "携程商旅",
    }
    if existing:
        existing.columns, existing.rows, existing.mapping = columns, rows, mapping
    else:
        db.add(ChannelData(channel_id=ch.id, columns=columns, rows=rows, mapping=mapping))
    db.commit()

    # 按映射汇入经营数据表（覆盖式、幂等），联动看板/大屏图表
    from app.services.channel_etl import sync_channel_to_operation
    sync_channel_to_operation(db, ch, columns, rows, mapping)


def seed_invoices(db: Session) -> None:
    if db.scalar(select(Invoice).limit(1)):
        return
    demo = [
        {"invoice_title": "济南新华书店有限公司", "tax_no": "91370100MA3XXXXX01", "amount": 1800000, "status": InvoiceStatus.ISSUED, "customer_name": "济南新华书店有限公司", "contract_no": "HT-2026-001", "issued_date": None, "remark": "教材印制"},
        {"invoice_title": "青岛出版发行集团", "tax_no": "91370200MA3XXXXX02", "amount": 600000, "status": InvoiceStatus.PENDING, "customer_name": "青岛出版发行集团", "contract_no": "HT-2026-002", "remark": "技术服务"},
        {"invoice_title": "齐鲁印刷有限公司", "tax_no": "91370100MA3XXXXX03", "amount": 450000, "status": InvoiceStatus.PENDING, "customer_name": "齐鲁印刷有限公司", "contract_no": "HT-2026-003", "remark": "物流仓储"},
    ]
    for d in demo:
        db.add(Invoice(**d))
    db.commit()


def seed_finance_config(db: Session) -> None:
    """确保存在一行投入成本配置（默认 0，由领导在经营页录入真实值）。"""
    if db.scalar(select(FinanceConfig).limit(1)):
        return
    db.add(FinanceConfig(total_invested_cost=Decimal("0")))
    db.commit()


def init() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_users(db)
        seed_operation(db)
        seed_customers(db)
        seed_channels(db)
        seed_channel_data(db)
        seed_invoices(db)
        seed_finance_config(db)
        print("数据库初始化完成：已建表并写入种子数据。")
        print("默认账号(密码均为 123456)：")
        print("  admin(超管) / op(业务经办) / scm(供管公司负责人) / legal(法律顾问)")
        print("  risk(投资公司法务风控) / inv(投资公司分管领导) / review / fin / finr")
    finally:
        db.close()


if __name__ == "__main__":
    init()
