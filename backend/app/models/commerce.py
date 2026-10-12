"""商品、货盘、采购、资金流水、促销、投流。

金额一律以「分」为单位的 Integer 存储（规避浮点误差）；
资金变动统一经 services/fund.py 写 FundTxn 流水，保证可审计。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class Product(Base):
    """平台商品库（内置 + 教师/管理员维护），学生也可在场次内添加自定义商品。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    brand: Mapped[str] = mapped_column(String(128), default="")
    category: Mapped[str] = mapped_column(String(128), index=True)
    cost_cents: Mapped[int] = mapped_column(Integer)  # 成本价
    market_price_cents: Mapped[int] = mapped_column(Integer)  # 市场参考价
    heat: Mapped[float] = mapped_column(Float, default=5.0)  # 热度 1-10
    stock: Mapped[int] = mapped_column(Integer, default=0)  # 可售库存
    images: Mapped[list] = mapped_column(JSON, default=list)
    selling_points: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="on")  # on / off
    source: Mapped[str] = mapped_column(String(16), default="builtin")  # builtin / custom
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SessionItem(Base):
    """场次货盘中的一款商品（含定位、图文、定价、库存）。"""

    __tablename__ = "session_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True
    )
    # 自定义商品快照（product_id 为空时使用）
    custom_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    custom_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    role: Mapped[str] = mapped_column(String(16), default="traffic")  # ItemRole
    status: Mapped[str] = mapped_column(String(16), default="editing")  # ItemStatus

    title: Mapped[str] = mapped_column(String(200), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    images: Mapped[list] = mapped_column(JSON, default=list)
    selling_points: Mapped[list] = mapped_column(JSON, default=list)
    detail: Mapped[str] = mapped_column(Text, default="")

    list_price_cents: Mapped[int] = mapped_column(Integer, default=0)  # 划线价
    live_price_cents: Mapped[int] = mapped_column(Integer, default=0)  # 直播价
    stock: Mapped[int] = mapped_column(Integer, default=0)  # 本场可售库存
    purchased_qty: Mapped[int] = mapped_column(Integer, default=0)  # 已采购数量
    purchase_unit_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sort: Mapped[int] = mapped_column(Integer, default=0)  # 讲解顺序
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Purchase(Base):
    """采购单：根据供应商报价与可用资金形成采购决策。"""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("session_items.id"), index=True)
    supplier: Mapped[str] = mapped_column(String(128), default="")
    qty: Mapped[int] = mapped_column(Integer)
    unit_cost_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FundTxn(Base):
    """资金流水：任何余额变化都有据可查（采购 / 投流 / 销售回款 / 退款）。"""

    __tablename__ = "fund_txns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    type: Mapped[str] = mapped_column(String(16), index=True)  # FundTxnType
    amount_cents: Mapped[int] = mapped_column(Integer)  # 有符号：负数为支出
    balance_after_cents: Mapped[int] = mapped_column(Integer)
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Promotion(Base):
    """促销配置：优惠券 / 满减 / 秒杀 / 赠品 / 拼团 / 抽奖。"""

    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))  # PromotionType
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # 活动目标/适用商品/预算等
    budget_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # PromotionStatus
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdPlan(Base):
    """流量推广计划：渠道 / 预算 / 人群 / 出价 / 优化目标。"""

    __tablename__ = "ad_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32))  # AdChannel
    objective: Mapped[str] = mapped_column(String(32))  # AdObjective
    budget_cents: Mapped[int] = mapped_column(Integer)
    spent_cents: Mapped[int] = mapped_column(Integer, default=0)
    audience: Mapped[dict] = mapped_column(JSON, default=dict)  # 地区/年龄/性别/兴趣
    creative: Mapped[str] = mapped_column(Text, default="")
    bid_cents: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # AdStatus
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
