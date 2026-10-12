"""直播事件流、订单、物流、售后。

LiveEvent 是直播过程的统一时间线（口播/行为采样/弹幕/回复/控制动作/订单/违规/AI 决策/指标快照），
自增 id 同时充当前端增量拉取的游标（since_id）。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class LiveEvent(Base):
    __tablename__ = "live_events"
    __table_args__ = (Index("ix_live_events_session_id_id", "session_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)  # LiveEventType
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)  # rule / llm / manual ...


class Order(Base):
    """模拟订单（不连接真实支付）。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("session_items.id"), index=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True)
    product_name: Mapped[str] = mapped_column(String(200), default="")  # 下单时快照
    qty: Mapped[int] = mapped_column(Integer, default=1)
    amount_cents: Mapped[int] = mapped_column(Integer)
    buyer_name: Mapped[str] = mapped_column(String(64), default="")
    buyer_persona: Mapped[str | None] = mapped_column(String(32), nullable=True)  # AI 观众人群
    status: Mapped[str] = mapped_column(String(16), default="pending_ship", index=True)  # OrderStatus
    logistics_node: Mapped[str | None] = mapped_column(String(16), nullable=True)  # LogisticsNode
    logistics_history: Mapped[list] = mapped_column(JSON, default=list)  # [{node, at, note}]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AfterSale(Base):
    """售后工单：退款 / 退货 / 换货 / 投诉 / 超卖 / 延迟发货。"""

    __tablename__ = "after_sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))  # AfterSaleType
    reason: Mapped[str] = mapped_column(Text, default="")
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # AfterSaleStatus
    handler_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    handler_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
