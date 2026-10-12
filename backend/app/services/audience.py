"""AI 观众决策模块。

按随机时间间隔，把近期口播、当前商品、价格、库存、卖点、直播间设置、
在线人数与近期弹幕组织为上下文，生成评论、疑问和模拟购买决策；
每轮决策写入 ai_decision 事件（输入摘要 / 生成结果 / 理由 / 实际创建订单数），可回溯。

规则模板兜底时 source="rule"；配置 LLM 且调用成功时 source="llm"。
"""

import logging
import random
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session as OrmSession

from app.core.enums import FundTxnType, LiveEventType, OrderStatus
from app.core.config import get_settings
from app.models.commerce import SessionItem
from app.models.live import LiveEvent, Order
from app.models.task import TrainingSession
from app.services import ai, fund
from app.prompts import templates as prompts

logger = logging.getLogger(__name__)

# 顾客画像：扩展示例（题目：价格敏感型/成分关注型/售后关注型/犹豫型/高意向型）
PERSONAS: list[dict[str, Any]] = [
    {
        "code": "price_sensitive",
        "name": "价格敏感型",
        "weight": 0.25,
        "remarks": [
            "这个价格还能再便宜点吗？",
            "有没有优惠券可以领呀？",
            "买两件能不能更划算？",
        ],
    },
    {
        "code": "ingredient",
        "name": "成分关注型",
        "weight": 0.15,
        "remarks": [
            "成分表可以看一下吗？",
            "这款适合敏感肌吗？",
            "保质期和生产日期是什么时候？",
        ],
    },
    {
        "code": "after_sale",
        "name": "售后关注型",
        "weight": 0.15,
        "remarks": [
            "支持七天无理由退货吗？",
            "发什么快递，大概几天到？",
            "坏了可以换新吗？",
        ],
    },
    {
        "code": "hesitant",
        "name": "犹豫型",
        "weight": 0.25,
        "remarks": [
            "我再看看，先加购物车吧",
            "和别人家比哪个更值？",
            "效果真的有这么好吗？",
        ],
    },
    {
        "code": "high_intent",
        "name": "高意向型",
        "weight": 0.20,
        "remarks": [
            "怎么下单？要几号链接？",
            "直接拍这个链接就行吗？",
            "库存还有吗？想拍两件",
        ],
    },
]


def _pick_persona(rng: random.Random) -> dict[str, Any]:
    codes = [p["code"] for p in PERSONAS]
    weights = [p["weight"] for p in PERSONAS]
    code = rng.choices(codes, weights=weights, k=1)[0]
    return next(p for p in PERSONAS if p["code"] == code)


def _recent_speeches(db: OrmSession, session_id: int, limit: int = 3) -> list[str]:
    rows = db.execute(
        select(LiveEvent)
        .where(LiveEvent.session_id == session_id, LiveEvent.type == LiveEventType.SPEECH)
        .order_by(desc(LiveEvent.id))
        .limit(limit)
    ).scalars().all()
    return [((r.payload or {}).get("text") or "") for r in rows]


def _rule_comments(
    rng: random.Random, item: SessionItem | None, recent_speech: list[str], online: int
) -> list[dict[str, str]]:
    """规则兜底：按画像权重挑人设，结合当前商品生成弹幕。"""
    n = rng.choices([0, 1, 2, 3], weights=[0.2, 0.4, 0.25, 0.15], k=1)[0]
    if online <= 0:
        n = 0
    out: list[dict[str, str]] = []
    for _ in range(n):
        persona = _pick_persona(rng)
        text = rng.choice(persona["remarks"])
        if item is not None:
            name = item.title or item.custom_name or "这款商品"
            if persona["code"] == "price_sensitive" and item.live_price_cents:
                text = f"{name}这个价还能再低吗？{text}"
            elif persona["code"] == "high_intent" and item.stock > 0:
                text = f"{text}（{name}）"
            elif persona["code"] == "hesitant" and item.selling_points:
                text = f"{name}的「{item.selling_points[0]}」是真的吗？"
        if recent_speech and rng.random() < 0.3:
            snippet = recent_speech[0][:20]
            text = f"刚刚说的{snippet}…？" + text
        out.append({"persona": persona["code"], "text": text})
    return out


def _llm_comments(context: dict) -> tuple[list[dict[str, str]], str]:
    data, source = ai.chat_json(
        prompts.audience_comment(context),
        system=prompts.AUDIENCE_SYSTEM,
        timeout=get_settings().llm_audience_timeout_seconds,
    )
    comments = data.get("comments") or []
    if not isinstance(comments, list):
        raise ValueError("comments 字段类型错误")
    return [
        {"persona": str(c.get("persona", "hesitant")), "text": str(c.get("text", ""))[:200]}
        for c in comments
        if c.get("text")
    ], source


def step(
    db: OrmSession,
    session: TrainingSession,
    rng: random.Random,
    snapshot: dict,
) -> list[LiveEvent]:
    """推进一轮 AI 观众决策，返回新增事件。"""
    current_item_id = snapshot.get("current_item_id")
    item: SessionItem | None = None
    if current_item_id:
        item = db.get(SessionItem, current_item_id)
    if item is None:
        item = db.execute(
            select(SessionItem)
            .where(SessionItem.session_id == session.id, SessionItem.status == "listed")
            .order_by(SessionItem.sort)
            .limit(1)
        ).scalar_one_or_none()

    recent_speech = _recent_speeches(db, session.id)
    recent_comments = db.execute(
        select(LiveEvent)
        .where(LiveEvent.session_id == session.id, LiveEvent.type == LiveEventType.COMMENT)
        .order_by(desc(LiveEvent.id))
        .limit(5)
    ).scalars().all()

    context = {
        "online": snapshot.get("online", 0),
        "current_item": None
        if item is None
        else {
            "name": item.title or item.custom_name,
            "live_price_cents": item.live_price_cents,
            "stock": item.stock,
            "selling_points": item.selling_points,
        },
        "recent_speech": recent_speech,
        "recent_comments": [((c.payload or {}).get("text") or "") for c in recent_comments],
        "room": {
            "welcome": (session.room_config or {}).get("welcome", ""),
            "notice": (session.room_config or {}).get("notice", ""),
        },
    }

    source = "rule"
    reason = "规则兜底：按画像权重与当前商品生成"
    comments = _rule_comments(rng, item, recent_speech, snapshot.get("online", 0))
    # 推理模型较慢：按 N 个 tick 降频调用，超时（llm_audience_timeout_seconds）即规则兜底，
    # 保证直播节奏不被模型延迟拖垮
    tick_count = int(snapshot.get("tick_count", 0))
    every_n = max(1, get_settings().llm_audience_every_n_ticks)
    if ai.is_llm_configured() and snapshot.get("online", 0) > 0 and tick_count % every_n == 0:
        try:
            comments, source = _llm_comments(context)
            reason = "大模型依据场次上下文生成"
        except (ai.AiUnavailable, ValueError) as exc:
            logger.warning("AI 观众调用失败，降级规则生成：%s", exc)
            source = "rule"

    events: list[LiveEvent] = []
    for c in comments:
        if not c["text"]:
            continue
        events.append(
            LiveEvent(
                session_id=session.id,
                type=LiveEventType.COMMENT,
                payload={
                    "text": c["text"],
                    "persona": c["persona"],
                    "simulated": True,  # 明确标识：教学仿真观众
                },
                source=source,
            )
        )
    for ev in events:
        db.add(ev)
    if events:
        db.flush()

    # 高意向观众可能直接下单（模拟购买决策）
    created_orders = 0
    if item is not None and item.status == "listed" and item.stock > 0:
        high_intent = sum(1 for c in comments if c["persona"] == "high_intent")
        extra_chance = 0.25 * high_intent + 0.05
        if rng.random() < extra_chance:
            qty = min(1 + (1 if rng.random() < 0.2 else 0), item.stock)
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
                buyer_persona="high_intent",
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
                note="AI 观众高意向下单",
            )
            db.add(
                LiveEvent(
                    session_id=session.id,
                    type=LiveEventType.ORDER,
                    payload={
                        "order_id": order.id,
                        "order_no": order.order_no,
                        "amount_cents": amount,
                        "persona": "high_intent",
                    },
                    source=source,
                )
            )
            created_orders += 1
            if item.stock == 0:
                item.status = "editing"
                db.add(
                    LiveEvent(
                        session_id=session.id,
                        type=LiveEventType.SYSTEM,
                        payload={"text": f"「{order.product_name}」库存售罄，已自动下架"},
                        source="rule",
                    )
                )
            db.flush()

    # 每轮决策记录：输入摘要 / 生成结果 / 理由 / 实际创建订单数
    db.add(
        LiveEvent(
            session_id=session.id,
            type=LiveEventType.AI_DECISION,
            payload={
                "input_summary": {
                    "online": context["online"],
                    "current_item": None if item is None else context["current_item"]["name"],
                    "recent_speech_count": len(recent_speech),
                    "recent_comment_count": len(context["recent_comments"]),
                },
                "result": [c["text"] for c in comments],
                "reason": reason,
                "created_orders": created_orders,
            },
            source=source,
        )
    )
    db.flush()
    return events
