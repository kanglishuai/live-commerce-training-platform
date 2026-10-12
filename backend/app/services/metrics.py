"""数据罗盘：从事件流与订单聚合教学指标（概况/销售/流量/用户四个视角）。

题目要求“统计界面显示数据来源和估算口径，样本不足时不强行生成趋势”，
因此返回值包含 notes，明确哪些是仿真数据、哪些是估算值。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.enums import AfterSaleStatus, AfterSaleType, LiveEventType
from app.models.commerce import AdPlan, SessionItem
from app.models.live import AfterSale, LiveEvent, Order
from app.models.task import TrainingSession
from app.services.audience import PERSONAS

MIN_TREND_TICKS = 3  # 少于 3 个采样点不输出趋势


def _overview(db: OrmSession, session: TrainingSession) -> dict:
    m = session.metrics or {}
    viewers = int(m.get("viewers", 0))
    clicks = int(m.get("item_clicks", 0))
    order_count = int(m.get("orders", 0))
    gmv = int(m.get("gmv_cents", 0))
    likes = int(m.get("likes", 0))
    comments = int(m.get("comments", 0))
    violations = int(
        db.execute(
            select(func.count(LiveEvent.id)).where(
                LiveEvent.session_id == session.id, LiveEvent.type == LiveEventType.VIOLATION
            )
        ).scalar_one()
    )
    refund_orders = int(
        db.execute(
            select(func.count(AfterSale.id)).where(
                AfterSale.session_id == session.id,
                AfterSale.type == AfterSaleType.REFUND,
                AfterSale.status.in_([AfterSaleStatus.APPROVED, AfterSaleStatus.CLOSED]),
            )
        ).scalar_one()
    )
    settled = int(
        db.execute(
            select(func.count(Order.id)).where(
                Order.session_id == session.id, Order.status.in_(["signed", "closed"])
            )
        ).scalar_one()
    )
    return {
        "viewers": viewers,
        "peak_online": int(m.get("peak_online", 0)),
        "online": int(m.get("online", 0)),
        "item_clicks": clicks,
        "click_rate": round(clicks / viewers, 4) if viewers else 0.0,
        "orders": order_count,
        "conversion_rate": round(order_count / clicks, 4) if clicks else 0.0,
        "gmv_cents": gmv,
        "aov_cents": round(gmv / order_count) if order_count else 0,
        "interaction_rate": round((likes + comments) / viewers, 4) if viewers else 0.0,
        "new_fans_estimate": int(viewers * 0.05),
        "refund_orders": refund_orders,
        "refund_rate": round(refund_orders / order_count, 4) if order_count else 0.0,
        "ship_settled": settled,
        "tick_count": int(m.get("tick_count", 0)),
        "violations": violations,
    }


def _sales(db: OrmSession, session: TrainingSession) -> dict:
    rows = db.execute(
        select(Order.item_id, func.count(Order.id), func.sum(Order.amount_cents))
        .where(Order.session_id == session.id)
        .group_by(Order.item_id)
    ).all()
    item_names = {
        i.id: (i.title or i.custom_name or f"商品{i.id}")
        for i in db.execute(
            select(SessionItem).where(SessionItem.session_id == session.id)
        ).scalars().all()
    }
    contribution = [
        {
            "item_id": item_id,
            "name": item_names.get(item_id, f"商品{item_id}"),
            "orders": int(cnt),
            "amount_cents": int(amount or 0),
        }
        for item_id, cnt, amount in rows
    ]
    contribution.sort(key=lambda x: x["amount_cents"], reverse=True)

    ticks = db.execute(
        select(LiveEvent.payload)
        .where(LiveEvent.session_id == session.id, LiveEvent.type == LiveEventType.METRIC)
        .order_by(LiveEvent.id)
    ).scalars().all()
    trend = [
        {
            "tick": p.get("tick"),
            "online": p.get("online"),
            "clicks": p.get("clicks"),
            "orders": p.get("orders_this_tick"),
            "gmv_cents": p.get("gmv_cents"),
        }
        for p in ticks
    ]
    overview = _overview(db, session)
    funnel = {
        "viewers": overview["viewers"],
        "clicks": overview["item_clicks"],
        "orders": overview["orders"],
        "click_rate": overview["click_rate"],
        "conversion_rate": overview["conversion_rate"],
    }
    return {
        "trend": trend if len(trend) >= MIN_TREND_TICKS else [],
        "trend_sufficient": len(trend) >= MIN_TREND_TICKS,
        "item_contribution": contribution,
        "funnel": funnel,
    }


def _traffic(db: OrmSession, session: TrainingSession) -> dict:
    m = session.metrics or {}
    plans = db.execute(
        select(AdPlan).where(AdPlan.session_id == session.id)
    ).scalars().all()
    spend_total = sum(p.spent_cents for p in plans)
    gmv = int(m.get("gmv_cents", 0))
    viewers = int(m.get("viewers", 0))
    by_channel: dict[str, dict] = {}
    for p in plans:
        c = by_channel.setdefault(
            p.channel, {"channel": p.channel, "budget_cents": 0, "spent_cents": 0, "plans": 0}
        )
        c["budget_cents"] += p.budget_cents
        c["spent_cents"] += p.spent_cents
        c["plans"] += 1
    return {
        "ad_spend_cents": spend_total,
        "ad_spend_from_ledger_cents": int(m.get("ad_spend_cents", 0)),
        "channels": list(by_channel.values()),
        "roas": round(gmv / spend_total, 2) if spend_total else None,
        "estimated_organic_viewers": max(0, viewers - int(spend_total / 100)),
        "estimated_ad_viewers": int(spend_total / 100),
    }


def _users(db: OrmSession, session: TrainingSession) -> dict:
    rows = db.execute(
        select(Order.buyer_persona, func.count(Order.id))
        .where(Order.session_id == session.id, Order.buyer_persona.is_not(None))
        .group_by(Order.buyer_persona)
    ).all()
    persona_orders = {p: int(c) for p, c in rows if p}
    personas = {p["code"]: int(p["weight"] * 100) for p in PERSONAS}
    return {
        "persona_audience_mix": personas,  # AI 观众人群构成（仿真设定）
        "persona_orders": persona_orders,
        "notes": "人群构成为教学仿真设定，不代表真实用户分布",
    }


_VIEWS = {"overview": _overview, "sales": _sales, "traffic": _traffic, "users": _users}

NOTES = [
    "观众、订单、资金、物流均为教学仿真数据，不连接真实支付。",
    "广告进房人数按“每 1 元约 1 人”的换算口径估算，仅用于教学分析。",
    "新增粉丝、渠道占比为估算值，样本不足时不输出趋势（需 ≥3 个采样点）。",
]


def build(db: OrmSession, session: TrainingSession, view: str) -> tuple[dict, list[str]]:
    fn = _VIEWS.get(view)
    if fn is None:
        from app.core import errors

        raise errors.validation_error(f"未知视角 {view}，可选：{'/'.join(_VIEWS)}")
    return fn(db, session), NOTES
