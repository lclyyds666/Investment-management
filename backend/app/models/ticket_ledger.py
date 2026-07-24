"""文旅业务·门票平台核销业务台账模型（按 scenic_id 严格数据隔离）。

每行 = 一个对账明细文件（含多周 Sheet）汇总为一期台账。
计算列（景区核销/服务费/结算金额）由「出版应得到账金额」按比例算出并落库；
固定/手工字段（付款日期、平台、回款等）随行保存。金额统一以元存储 Numeric(18,2)。
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TicketLedger(Base):
    __tablename__ = "biz_ticket_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    # 景区作用域键：数据隔离核心，按景区过滤
    scenic_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="景区ID(作用域键)"
    )
    row_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="行序(稳定排序)")

    # —— 固定 / 手工录入字段 ——
    pay_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="付款日期(手工)")
    platform: Mapped[str] = mapped_column(String(32), default="", comment="平台(抖音/美团/携程/同程,手工)")
    ticket_product: Mapped[str] = mapped_column(
        String(200), default="水上世界/童话世界/海洋王国", comment="景区门票产品名(默认固定)"
    )
    check_date_text: Mapped[str] = mapped_column(String(64), default="", comment="核对日期(自动,周期跨度)")
    period_text: Mapped[str] = mapped_column(String(64), default="", comment="对账周期文本(自动)")
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True, comment="对账周期起(自动)")
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True, comment="对账周期止(自动)")

    # —— 计算相关字段 ——
    supplier_received: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="服务商到账金额(明细算:订单实收-软件-达人-团长)"
    )
    supplier_commission: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="服务商佣金(手工录入,默认0)"
    )
    publisher_due: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="出版应得到账金额 B = 服务商到账 - 服务商佣金(计算基数)"
    )
    hexiao_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="景区核销金额 = B × 核销率"
    )
    # 付款金额(手工录入,仅待确认台账录入) + 景区待核销金额(滚动余额,后端集中记录)
    payment_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="付款金额(手工录入,期次递推输入)"
    )
    pending_writeoff: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0,
        comment="景区待核销金额(滚动余额)=上期余额+本期付款金额-本期景区核销金额",
    )
    jinying_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="结算金额 = B × 结算费率"
    )
    service_fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="服务费 = 结算金额 − 景区核销金额"
    )
    rate_hexiao: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.9000"), comment="景区核销率(默认0.90)"
    )
    rate_settle: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.9400"), comment="结算费率(默认0.94,结算金额=B×结算费率)"
    )
    rate_fee: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.0400"), comment="旧服务费率(已弃用,保留历史列)"
    )
    order_count: Mapped[int] = mapped_column(Integer, default=0, comment="核销订单数(明细统计)")
    positive_count: Mapped[int] = mapped_column(Integer, default=0, comment="订单实收为正数的订单数(核销率分子)")

    # —— 回款（手工录入）——
    repay_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="回款日期(手工)")
    repay_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True, comment="回款金额(手工)"
    )

    # 逐日明细(JSON)：每天聚合后的到账/实收/达人/团长，供编辑改费率/佣金时逐日重算累加
    daily_json: Mapped[str] = mapped_column(Text, nullable=True, comment="逐日明细JSON(供逐日重算)")
    # 确认函(按期共享；同期各行同值)：有则状态=已确认，无则未确认。仅业务复核/信息维护可维护
    confirm_stored: Mapped[str] = mapped_column(String(255), default="", comment="确认函磁盘存储名(uuid)")
    confirm_name: Mapped[str] = mapped_column(String(255), default="", comment="确认函原始文件名")

    source_file: Mapped[str] = mapped_column(String(255), default="", comment="来源Excel文件名")
    # 明细源文件落盘(供预览/下载)：detail_stored=磁盘uuid文件名, detail_name=原始文件名
    detail_stored: Mapped[str] = mapped_column(String(255), default="", comment="明细文件磁盘存储名(uuid)")
    detail_name: Mapped[str] = mapped_column(String(255), default="", comment="明细文件原始名")
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id"), nullable=True, comment="上传/创建人"
    )
