"""文旅业务·景区酒店平台核销业务台账模型（按 scenic_id 严格数据隔离）。

一份对账明细文件 = 一期，内含多个平台（抖音/美团/携程…）→ 每平台一行。
计算逻辑（已用泉州欧乐堡真实业务台账 6 期反推验证）：
- 各平台「结算基数」settle_base = base_received − commission
    · 抖音：base_received = 服务商到账 = Σ(订单实收−软件−达人−团长)=−Σ服务商服务费；
            commission = 服务商佣金(默认 订单实收×6%−达人−团长，可手工微调)；settle_base = 出版应得到账。
    · 美团：base_received = Σ结算金额(毛额)；commission=0；settle_base=结算金额。
    · 携程：base_received = Σ结算价(毛额)；commission=0；settle_base=结算价。
- 景区核销金额 hexiao = settle_base × 核销率(默认0.90)
- 服务费/结算金额 两种算法（fee_algo）：
    算法1(默认)：服务费 = 间夜 × 每间夜服务费(44)；结算金额 = 核销 + 服务费。
    算法2       ：结算金额 = 结算基数 × 结算费率(rate_settle,默认0.94)；服务费 = 结算金额 − 核销。
- 景区待核销金额 pending_writeoff：**按整期滚动**（每期一个余额，存于该期各平台行）
    首期 = 本期付款 − 本期各平台核销合计；续期 = 上期余额 + 本期付款 − 本期各平台核销合计。
付款金额/回款日期/回款金额 **每期各平台共享**（同期各行同值，手工录入；付款隐藏、留存，参与递推）。
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HotelLedger(Base):
    __tablename__ = "biz_hotel_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    scenic_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="景区ID(作用域键)"
    )
    row_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="行序(稳定排序)")

    # —— 维度 ——
    platform: Mapped[str] = mapped_column(String(32), default="", comment="平台(抖音/美团/携程)")
    hotel_name: Mapped[str] = mapped_column(String(255), default="", comment="酒店名称")
    check_date_text: Mapped[str] = mapped_column(String(64), default="", comment="核对日期(周期跨度)")
    period_text: Mapped[str] = mapped_column(String(64), default="", comment="对账周期文本")
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True, comment="对账周期起(排序键)")
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True, comment="对账周期止")

    # —— 计算相关 ——
    room_nights: Mapped[int] = mapped_column(Integer, default=0, comment="间夜数(明细统计)")
    base_received: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="平台结算原值(抖音=服务商到账;美团/携程=平台结算毛额)"
    )
    supplier_commission: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="服务商佣金(仅抖音;默认订单实收×6%−达人−团长,可编辑)"
    )
    settle_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="结算基数=base_received−佣金(抖音=出版应得;美团/携程=毛额)"
    )
    rate_hexiao: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.9000"), comment="景区核销率(默认0.90)"
    )
    hexiao_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="景区核销金额 = 结算基数 × 核销率"
    )
    fee_algo: Mapped[int] = mapped_column(
        Integer, default=1, comment="服务费算法(1=间夜×每间夜服务费;2=结算金额−核销)"
    )
    fee_per_night: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("44.00"), comment="每间夜服务费(默认44元,算法1)"
    )
    rate_settle: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.9400"), comment="结算费率(默认0.94,算法2:结算=结算基数×结算费率)"
    )
    service_fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="服务费(算法1=间夜×每间夜服务费;算法2=结算金额−核销)"
    )
    jinying_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="结算金额(算法1=核销+服务费;算法2=结算基数×结算费率)"
    )

    # —— 付款/待核销（付款隐藏但留存；待核销按平台滚动余额）——
    payment_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="付款金额(手工,隐藏,参与递推)"
    )
    pending_writeoff: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="景区待核销金额(按平台滚动余额)"
    )

    # —— 回款（手工）——
    repay_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="回款日期(手工)")
    repay_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True, comment="回款金额(手工)"
    )

    order_count: Mapped[int] = mapped_column(Integer, default=0, comment="订单数(明细统计)")
    # 逐日明细(JSON)：每天到账/毛额/实收/达人/团长/间夜，供编辑改费率/佣金/算法时逐日重算累加
    daily_json: Mapped[str] = mapped_column(Text, nullable=True, comment="逐日明细JSON(供逐日重算)")
    source_file: Mapped[str] = mapped_column(String(255), default="", comment="来源Excel文件名")
    detail_stored: Mapped[str] = mapped_column(String(255), default="", comment="明细文件磁盘存储名(uuid)")
    detail_name: Mapped[str] = mapped_column(String(255), default="", comment="明细文件原始名")
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id"), nullable=True, comment="上传/创建人"
    )
