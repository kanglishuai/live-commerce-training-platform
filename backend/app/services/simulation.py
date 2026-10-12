"""直播仿真引擎。

设计决策（见 探索记录.md 未知项 1）：不引入后台任务/消息队列，
由前端按周期调用 POST /live/tick 推进；服务端用最小间隔防误刷。
好处：无中间件依赖、演示可暂停可复现、tick 步进与前端刷新天然对齐。

所有观众、订单、金额、物流均为教学模拟，不连接真实支付。
可调参数集中在 SIM_PARAMS，教师可按教学需要调整（后续可外置到任务配置）。
"""

import random
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core import errors
from app.core.config import get_settings
from app.core.enums import (
    AdStatus,
    FundTxnType,
    ItemStatus,
    LiveEventType,
    OrderStatus,
    SessionStatus,
)
from app.db.base import utcnow
from app.models.commerce import AdPlan, Promotion, SessionItem
from app.models.live import LiveEvent, Order
from app.models.task import Task, TrainingSession
from app.services import audience, fund

SIM_PARAMS = {
    # 自然流量：每 tick 进房人数基数 × 热度放大 × 竞争折减
    "organic_base_per_tick": 18.0,
    "heat_multiplier_min": 0.5,
    "heat_multiplier_span": 1.5,  # 热度 1-10 → 0.5 ~ 2.0 倍
    "competition_discount": 0.05,  # 竞争难度每 1 级折减 5%（1-10 级）
    "leave_rate": 0.12,  # 每 tick 在线流失率
    # 投流换算：每 1 元花费约带来 1 名进房（按优化目标修正）
    "ad_cost_per_view_cents": 100,
    "ad_objective_factor": {"exposure": 0.3, "click": 0.6, "enter_room": 1.0, "order": 1.2},
    "ad_spend_ratio_range": (0.08, 0.16),  # 每 tick 消耗预算比例
    # 点击与转化
    "ctr_base": 0.06,
    "ctr_price_bonus": 0.05,  # 直播价低于市场价
    "ctr_promo_bonus": 0.03,  # 有生效促销
    "ctr_item_bonus_cap": 0.03,  # 商品数量加成上限
    "cvr_base": 0.05,
    "cvr_promo_bonus": 0.03,
    "cvr_speech_bonus": 0.04,  # 最近 1 分钟内有口播
    "cvr_ad_order_bonus": 0.02,  # 有以“成交”为优化目标的投流
    "likes_per_10_online": (1, 5),  # 每 tick 每 10 在线点赞随机区间
    "multi_qty_chance": 0.08,  # 单笔多件的概率
}

SNAPSHOT_KEYS = (
    "online",
    "viewers",
    "peak_online",
    "likes",
    "comments",
    "item_clicks",
    "orders",
    "gmv_cents",
    "tick_count",
    "current_item_id",
)


def snapshot_of(session: TrainingSession) -> dict:
    m = session.metrics or {}
    return {k: m.get(k, 0) for k in SNAPSHOT_KEYS} | {"updated_at": m.get("updated_at")}


def latest_event_id(db: OrmSession, session_id: int) -> int:
    return int(
        db.execute(
            select(func.coalesce(func.max(LiveEvent.id), 0)).where(
                LiveEvent.session_id == session_id
            )
        ).scalar_one()
    )


def _count_events(db: OrmSession, session_id: int, event_type: str) -> int:
    return int(
        db.execute(
            select(func.count(LiveEvent.id)).where(
                LiveEvent.session_id == session_id, LiveEvent.type == event_type
            )
        ).scalar_one()
    )


def _recent_speech_count(db: OrmSession, session_id: int) -> int:
    """最近 1 分钟内是否有口播（影响转化率）。"""
    since = utcnow().timestamp() - 60
    rows = db.execute(
        select(LiveEvent.ts)
        .where(LiveEvent.session_id == session_id, LiveEvent.type == LiveEventType.SPEECH)
        .order_by(LiveEvent.id.desc())
        .limit(5)
    ).scalars().all()
    return sum(1 for ts in rows if ts.timestamp() >= since)


def _listed_items(db: OrmSession, session_id: int) -> list[SessionItem]:
    return list(
        db.execute(
            select(SessionItem)
            .where(SessionItem.session_id == session_id, SessionItem.status == ItemStatus.LISTED)
            .order_by(SessionItem.sort)
        ).scalars().all()
    )


def _choose_item(rng: random.Random, items: list[SessionItem]) -> SessionItem | None:
    """下单商品选择：折扣力度越大（直播价低于划线价）、定位为引流款的商品权重越高。"""
    available = [i for i in items if i.stock > 0 and i.live_price_cents > 0]
    if not available:
        return None
    weights: list[float] = []
    for i in available:
        w = 1.6 if i.role == "traffic" else 1.0
        if i.live_price_cents and i.list_price_cents:
            w *= 1.0 + max(0.0, (i.list_price_cents - i.live_price_cents) / i.list_price_cents)
        weights.append(w)
    return rng.choices(available, weights=weights, k=1)[0]


def _create_order(
    db: OrmSession,
    session: TrainingSession,
    item: SessionItem,
    qty: int,
    rng: random.Random,
    persona: str | None,
    source: str,
) -> Order:
    qty = max(1, min(qty, item.stock))
    amount = item.live_price_cents * qty
    item.stock -= qty
    order = Order(
        session_id=session.id,
        item_id=item.id,
        order_no=f"SO{session.id}-{uuid.uuid4().hex[:10].upper()}",
        product_name=item.title or item.custom_name or "",
        qty=qty,
        amount_cents=amount,
        buyer_name=f"模拟顾客{rng.randrange(100, 999)}",
        buyer_persona=persona,
        status=OrderStatus.PENDING_SHIP,
    )
    db.add(order)
    db.flush()
    fund.apply_fund_txn(
        db,
        session,
        FundTxnType.SALES_INCOME,
        amount,
        ref_type="order",
        ref_id=order.id,
        note="直播间成交（教学模拟）",
    )
    db.add(
        LiveEvent(
            session_id=session.id,
            type=LiveEventType.ORDER,
            payload={
                "order_id": order.id,
                "order_no": order.order_no,
                "product_name": order.product_name,
                "qty": qty,
                "amount_cents": amount,
                "persona": persona,
            },
            source=source,
        )
    )
    if item.stock == 0:
        item.status = ItemStatus.EDITING
        db.add(
            LiveEvent(
                session_id=session.id,
                type=LiveEventType.SYSTEM,
                payload={"text": f"「{order.product_name}」库存售罄，已自动下架"},
                source="rule",
            )
        )
    db.flush()
    return order


def tick(db: OrmSession, session_id: int, *, force: bool = False) -> dict:
    """推进一个仿真周期。

    返回 {status, snapshot, new_events, latest_event_id}；
    new_events 仅包含本 tick 内产生的事件（不含客户端在两次 tick 之间自行提交的
    口播/行为/控制事件，那些由 GET /live/events?since_id= 增量拉取）。
    """
    session = fund.lock_session(db, session_id)
    settings = get_settings()

    if session.status == SessionStatus.PAUSED:
        return {
            "status": session.status,
            "snapshot": snapshot_of(session),
            "new_events": [],
            "latest_event_id": latest_event_id(db, session.id),
        }
    if session.status != SessionStatus.LIVE:
        raise errors.AppError(
            errors.SESSION_NOT_LIVE,
            f"场次当前状态为 {session.status}，只有直播中才能推进仿真",
            400,
            {"current": session.status},
        )

    m = dict(session.metrics or {})
    now = utcnow()
    last_tick_at = m.get("last_tick_at")
    if last_tick_at and not force:
        elapsed = (now - datetime.fromisoformat(last_tick_at)).total_seconds()
        if elapsed < settings.sim_tick_min_interval_seconds:
            raise errors.AppError(
                errors.TICK_TOO_FREQUENT,
                f"tick 间隔过短：距上次 {elapsed:.2f}s，最小间隔 {settings.sim_tick_min_interval_seconds}s",
                429,
                {"elapsed_seconds": round(elapsed, 2)},
            )

    cursor = int(m.get("last_event_id", 0))
    orders_before = int(
        db.execute(
            select(func.count(Order.id)).where(Order.session_id == session.id)
        ).scalar_one()
    )

    tick_count = int(m.get("tick_count", 0)) + 1
    # 以 (场次, 周期) 为种子的伪随机：同一场次重放可复现，便于课堂复盘
    rng = random.Random(f"{session.id}:{tick_count}")
    task = db.get(Task, session.task_id)
    heat = task.market_heat if task else 5.0
    competition = task.competition_level if task else 5.0

    # ---- 投流：按 tick 消耗预算，换算为进房人数 ----
    ad_incoming = 0.0
    ad_spend_total = 0
    plans = db.execute(
        select(AdPlan).where(AdPlan.session_id == session.id, AdPlan.status == AdStatus.ACTIVE)
    ).scalars().all()
    for plan in plans:
        remaining = plan.budget_cents - plan.spent_cents
        if remaining <= 0:
            plan.status = AdStatus.STOPPED
            continue
        lo, hi = SIM_PARAMS["ad_spend_ratio_range"]
        spend = min(remaining, max(1, int(plan.budget_cents * rng.uniform(lo, hi))))
        fund.apply_fund_txn(
            db,
            session,
            FundTxnType.AD_SPEND,
            -spend,
            ref_type="ad_plan",
            ref_id=plan.id,
            note=f"投流消耗（{plan.channel}）",
        )
        plan.spent_cents += spend
        ad_spend_total += spend
        factor = SIM_PARAMS["ad_objective_factor"].get(plan.objective, 1.0)
        ad_incoming += spend / SIM_PARAMS["ad_cost_per_view_cents"] * factor
    ad_order_objective = any(p.objective == "order" for p in plans)

    # ---- 流量与在线 ----
    organic = (
        SIM_PARAMS["organic_base_per_tick"]
        * (SIM_PARAMS["heat_multiplier_min"] + heat / 10 * SIM_PARAMS["heat_multiplier_span"])
        * (1.0 - competition * SIM_PARAMS["competition_discount"])
    )
    incoming = max(0, int(organic * rng.uniform(0.8, 1.2) + ad_incoming * rng.uniform(0.8, 1.2)))
    online = int(m.get("online", 0) * (1 - SIM_PARAMS["leave_rate"]) + incoming)
    viewers = max(int(m.get("viewers", 0)) + incoming, online)
    peak_online = max(int(m.get("peak_online", 0)), online)

    # ---- 点击 ----
    items = _listed_items(db, session.id)
    promo_active = (
        db.execute(
            select(Promotion.id).where(
                Promotion.session_id == session.id, Promotion.status == "active"
            )
        ).first()
        is not None
    )
    price_bonus = (
        SIM_PARAMS["ctr_price_bonus"]
        if any(i.list_price_cents and i.live_price_cents < i.list_price_cents for i in items)
        else 0.0
    )
    item_bonus = min(SIM_PARAMS["ctr_item_bonus_cap"], 0.01 * len(items))
    ctr = (
        SIM_PARAMS["ctr_base"]
        + price_bonus
        + (SIM_PARAMS["ctr_promo_bonus"] if promo_active else 0)
        + item_bonus
    )
    clicks = int(online * ctr * rng.uniform(0.8, 1.2))

    # ---- 下单 ----
    speech_recent = _recent_speech_count(db, session.id)
    cvr = (
        SIM_PARAMS["cvr_base"]
        + (SIM_PARAMS["cvr_promo_bonus"] if promo_active else 0)
        + (SIM_PARAMS["cvr_speech_bonus"] if speech_recent > 0 else 0)
        + (SIM_PARAMS["cvr_ad_order_bonus"] if ad_order_objective else 0)
    )
    expected_orders = clicks * cvr
    order_count = int(expected_orders) + (1 if rng.random() < (expected_orders % 1) else 0)
    for _ in range(order_count):
        item = _choose_item(rng, items)
        if item is None:
            break
        qty = 1 + (1 if rng.random() < SIM_PARAMS["multi_qty_chance"] else 0)
        persona = "high_intent" if rng.random() < 0.3 else None
        _create_order(db, session, item, qty, rng, persona, source="rule")

    # ---- 点赞 / AI 观众决策（内部写 comment / order / ai_decision 事件）----
    likes = int(m.get("likes", 0)) + int(
        online / 10 * rng.randint(*SIM_PARAMS["likes_per_10_online"])
    )
    audience.step(
        db,
        session,
        rng,
        {
            "online": online,
            "current_item_id": m.get("current_item_id"),
            "tick_count": tick_count,
        },
    )

    # ---- 汇总快照（订单/成交以库内数据为准，AI 观众下单也被计入）----
    total_orders = int(
        db.execute(
            select(func.count(Order.id)).where(Order.session_id == session.id)
        ).scalar_one()
    )
    total_gmv = int(
        db.execute(
            select(func.coalesce(func.sum(Order.amount_cents), 0)).where(
                Order.session_id == session.id
            )
        ).scalar_one()
    )
    updated = {
        **m,
        "online": online,
        "viewers": viewers,
        "peak_online": peak_online,
        "likes": likes,
        "comments": _count_events(db, session.id, LiveEventType.COMMENT),
        "item_clicks": int(m.get("item_clicks", 0)) + clicks,
        "orders": total_orders,
        "gmv_cents": total_gmv,
        "tick_count": tick_count,
        "last_tick_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "ad_spend_cents": int(m.get("ad_spend_cents", 0)) + ad_spend_total,
    }
    session.metrics = updated
    db.flush()

    db.add(
        LiveEvent(
            session_id=session.id,
            type=LiveEventType.METRIC,
            payload={
                "tick": tick_count,
                "online": online,
                "viewers": viewers,
                "clicks": clicks,
                "orders_this_tick": total_orders - orders_before,
                "gmv_cents": total_gmv,
                "ad_spend_cents": ad_spend_total,
            },
            source="rule",
        )
    )
    db.flush()

    new_events = list(
        db.execute(
            select(LiveEvent)
            .where(LiveEvent.session_id == session.id, LiveEvent.id > cursor)
            .order_by(LiveEvent.id)
        ).scalars().all()
    )
    latest = latest_event_id(db, session.id)
    session.metrics = {**session.metrics, "last_event_id": latest}
    db.flush()

    return {
        "status": session.status,
        "snapshot": snapshot_of(session),
        "new_events": new_events,
        "latest_event_id": latest,
    }
