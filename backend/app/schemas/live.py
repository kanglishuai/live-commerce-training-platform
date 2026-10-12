"""直播仿真、订单、物流、售后相关模式。"""

from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import AfterSaleType, ControlAction, LogisticsNode, SpeechSource
from app.schemas.common import ORMModel, UtcDatetime


class LiveEventOut(ORMModel):
    id: int
    session_id: int
    type: str
    ts: UtcDatetime
    payload: dict = {}
    source: str | None = None


class SnapshotOut(BaseModel):
    """实时仿真快照（题设：观众/订单/资金/物流均为教学模拟数据）。"""

    online: int = 0
    viewers: int = 0
    likes: int = 0
    comments: int = 0
    item_clicks: int = 0
    orders: int = 0
    gmv_cents: int = 0
    tick_count: int = 0
    current_item_id: int | None = None
    updated_at: str | None = None


class LiveStateOut(BaseModel):
    session_id: int
    status: str
    snapshot: SnapshotOut
    latest_event_id: int = 0
    started_at: UtcDatetime | None = None
    ended_at: UtcDatetime | None = None


class LiveTickOut(BaseModel):
    session_id: int
    status: str
    snapshot: SnapshotOut
    new_events: list[LiveEventOut] = []
    latest_event_id: int = 0


class EventsOut(BaseModel):
    events: list[LiveEventOut]
    latest_event_id: int


class SpeechIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    source: SpeechSource = SpeechSource.MANUAL


class SpeechOut(BaseModel):
    event: LiveEventOut
    violation: bool = False  # 是否命中敏感词（同时写入 violation 事件）
    messages: list[str] = []  # 对前端的提示，如“已按场次证据保存”


class BehaviorIn(BaseModel):
    face_detected: bool
    smile_coef: float = Field(default=0.0, ge=0, le=1)


class ControlIn(BaseModel):
    action: ControlAction
    payload: dict = {}


class ReplyIn(BaseModel):
    comment_event_id: int
    text: str = Field(min_length=1, max_length=1000)


class ReplySuggestIn(BaseModel):
    comment_event_id: int


class ReplySuggestOut(BaseModel):
    text: str
    source: str  # llm / rule


class TranscribeOut(BaseModel):
    text: str
    source: str  # server_asr / rule


# ---- 订单 / 物流 / 售后 ----

class OrderOut(ORMModel):
    id: int
    session_id: int
    item_id: int
    order_no: str
    product_name: str
    qty: int
    amount_cents: int
    buyer_name: str
    buyer_persona: str | None = None
    status: str
    logistics_node: str | None = None
    logistics_history: list = []
    created_at: UtcDatetime
    shipped_at: UtcDatetime | None = None
    signed_at: UtcDatetime | None = None


class AfterSaleOut(ORMModel):
    id: int
    order_id: int
    session_id: int
    type: str
    reason: str
    amount_cents: int
    status: str
    handler_id: int | None = None
    handler_note: str
    created_at: UtcDatetime
    resolved_at: UtcDatetime | None = None


class OrderDetailOut(BaseModel):
    order: OrderOut
    after_sales: list[AfterSaleOut] = []


class ShipIn(BaseModel):
    note: str = ""


class LogisticsAdvanceIn(BaseModel):
    node: LogisticsNode
    note: str = ""


class AfterSaleCreateIn(BaseModel):
    order_id: int
    type: AfterSaleType
    reason: str = Field(min_length=1)
    amount_cents: int | None = Field(default=None, ge=0)


class AfterSaleResolveIn(BaseModel):
    action: Literal["approve", "reject"]
    note: str = ""


class AfterSaleCloseIn(BaseModel):
    note: str = ""
