"""商品、货盘、采购、资金、促销、投流相关模式。"""

from pydantic import BaseModel, Field, model_validator

from app.core.enums import (
    AdChannel,
    AdObjective,
    AdStatus,
    ItemRole,
    ItemStatus,
    PromotionStatus,
    PromotionType,
)
from app.schemas.common import ORMModel, UtcDatetime


# ---- 商品库 ----

class ProductCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand: str = ""
    category: str = Field(min_length=1, max_length=128)
    cost_cents: int = Field(ge=0)
    market_price_cents: int = Field(ge=0)
    heat: float = Field(default=5.0, ge=0, le=10)
    stock: int = Field(default=0, ge=0)
    images: list[str] = []
    selling_points: list[str] = []
    description: str = ""


class ProductPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    brand: str | None = None
    category: str | None = None
    cost_cents: int | None = Field(default=None, ge=0)
    market_price_cents: int | None = Field(default=None, ge=0)
    heat: float | None = Field(default=None, ge=0, le=10)
    stock: int | None = Field(default=None, ge=0)
    images: list[str] | None = None
    selling_points: list[str] | None = None
    description: str | None = None
    status: str | None = None


class ProductOut(ORMModel):
    id: int
    name: str
    brand: str
    category: str
    cost_cents: int
    market_price_cents: int
    heat: float
    stock: int
    images: list = []
    selling_points: list = []
    description: str
    status: str
    source: str
    created_at: UtcDatetime


# ---- 货盘 ----

class CartAddIn(BaseModel):
    product_id: int
    role: ItemRole


class CustomItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    cost_cents: int = Field(ge=0)
    market_price_cents: int = Field(default=0, ge=0)
    role: ItemRole = ItemRole.TRAFFIC
    images: list[str] = []
    selling_points: list[str] = []
    description: str = ""


class CartItemPatchIn(BaseModel):
    role: ItemRole | None = None
    title: str | None = Field(default=None, max_length=200)
    tags: list[str] | None = None
    images: list[str] | None = None
    selling_points: list[str] | None = None
    detail: str | None = None
    sort: int | None = None
    status: ItemStatus | None = None


class PricingIn(BaseModel):
    list_price_cents: int = Field(ge=0)  # 划线价
    live_price_cents: int = Field(ge=0)  # 直播价
    stock: int = Field(ge=0)

    @model_validator(mode="after")
    def check_prices(self) -> "PricingIn":
        if self.list_price_cents and self.live_price_cents > self.list_price_cents:
            raise ValueError("直播价不应高于划线价")
        return self


class CartItemOut(ORMModel):
    id: int
    session_id: int
    product_id: int | None = None
    name: str  # 商品名（自定义商品取 custom_name）
    role: str
    status: str
    title: str
    tags: list = []
    images: list = []
    selling_points: list = []
    detail: str
    list_price_cents: int
    live_price_cents: int
    stock: int
    purchased_qty: int
    purchase_unit_cost_cents: int | None = None
    cost_cents: int  # 成本（用于毛利提示）
    market_price_cents: int
    sort: int


class CartOut(BaseModel):
    session_id: int
    fund_balance_cents: int
    total_cost_cents: int  # 已采购成本合计
    items: list[CartItemOut]


class PurchaseIn(BaseModel):
    item_id: int
    qty: int = Field(ge=1)
    supplier: str = Field(default="", max_length=128)
    unit_cost_cents: int | None = Field(default=None, ge=0)  # 不传则取商品成本


class PurchaseOut(ORMModel):
    id: int
    session_id: int
    item_id: int
    supplier: str
    qty: int
    unit_cost_cents: int
    total_cents: int
    created_at: UtcDatetime


class PurchaseResultOut(BaseModel):
    purchase: PurchaseOut
    fund_balance_cents: int


class FundTxnOut(ORMModel):
    id: int
    session_id: int
    type: str
    amount_cents: int
    balance_after_cents: int
    ref_type: str | None = None
    ref_id: int | None = None
    note: str
    created_at: UtcDatetime


# ---- 促销与投流 ----

class PromotionIn(BaseModel):
    type: PromotionType
    config: dict = {}  # 活动目标/适用商品/预算或数量/开始条件
    budget_cents: int = Field(default=0, ge=0)


class PromotionOut(ORMModel):
    id: int
    session_id: int
    type: str
    config: dict = {}
    budget_cents: int
    status: str
    created_at: UtcDatetime


class PromotionPatchIn(BaseModel):
    status: PromotionStatus


class AdPlanIn(BaseModel):
    channel: AdChannel
    objective: AdObjective
    budget_cents: int = Field(gt=0)
    audience: dict = {}  # 地区/年龄/性别/兴趣
    creative: str = ""
    bid_cents: int = Field(default=100, ge=1)


class AdPlanOut(ORMModel):
    id: int
    session_id: int
    channel: str
    objective: str
    budget_cents: int
    spent_cents: int
    audience: dict = {}
    creative: str
    bid_cents: int
    status: str
    created_at: UtcDatetime


class AdPlanStatusIn(BaseModel):
    status: AdStatus
