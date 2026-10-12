"""订单履约与物流：发货、物流节点推进（状态机约束）、关闭订单。

拒收与退款会把商品退回库存；重复推进、状态回退会被拒绝。
"""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core import errors
from app.core.deps import CurrentUser, DbDep, assert_session_access, get_owned_session, get_session_or_404
from app.core.enums import LogisticsNode, OrderStatus
from app.db.base import utcnow
from app.models.commerce import SessionItem
from app.models.live import AfterSale, Order
from app.models.task import TrainingSession
from app.schemas.common import Page
from app.schemas.live import (
    AfterSaleOut,
    LogisticsAdvanceIn,
    OrderDetailOut,
    OrderOut,
    ShipIn,
)
from app.services import state_machines

router = APIRouter(tags=["订单与履约"])


def _get_order(db: DbDep, user: CurrentUser, order_id: int) -> tuple[Order, TrainingSession]:
    order = db.get(Order, order_id)
    if order is None:
        raise errors.not_found("订单", order_id)
    session = get_session_or_404(db, order.session_id)
    assert_session_access(db, user, session)
    return order, session


@router.get("/sessions/{session_id}/orders", response_model=Page[OrderOut], summary="订单列表")
def list_orders(
    session_id: int,
    user: CurrentUser,
    db: DbDep,
    status: OrderStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[OrderOut]:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    stmt, count_stmt = (
        select(Order).where(Order.session_id == session.id),
        select(func.count(Order.id)).where(Order.session_id == session.id),
    )
    if status is not None:
        stmt, count_stmt = stmt.where(Order.status == status), count_stmt.where(Order.status == status)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(Order.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[OrderOut](
        items=[OrderOut.model_validate(o) for o in rows], total=total, page=page, page_size=page_size
    )


@router.get("/orders/{order_id}", response_model=OrderDetailOut, summary="订单详情（含售后单）")
def get_order(order_id: int, user: CurrentUser, db: DbDep) -> OrderDetailOut:
    order, _ = _get_order(db, user, order_id)
    after_sales = db.execute(
        select(AfterSale).where(AfterSale.order_id == order.id).order_by(AfterSale.id)
    ).scalars().all()
    return OrderDetailOut(
        order=OrderOut.model_validate(order),
        after_sales=[AfterSaleOut.model_validate(a) for a in after_sales],
    )


@router.post("/orders/{order_id}/ship", response_model=OrderOut, summary="发货（进入物流）")
def ship_order(order_id: int, payload: ShipIn, user: CurrentUser, db: DbDep) -> OrderOut:
    order, session = _get_order(db, user, order_id)
    get_owned_session(db, user, session.id)  # 仅场次归属人可操作履约
    state_machines.assert_transition(
        state_machines.ORDER_TRANSITIONS, order.status, OrderStatus.SHIPPING, "订单"
    )
    order.status = OrderStatus.SHIPPING
    order.logistics_node = LogisticsNode.PICKED_UP
    order.shipped_at = utcnow()
    history = list(order.logistics_history or [])
    history.append({"node": str(LogisticsNode.PICKED_UP), "at": utcnow().isoformat(), "note": payload.note})
    order.logistics_history = history
    db.commit()
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/logistics/advance", response_model=OrderOut, summary="推进物流节点")
def advance_logistics(
    order_id: int, payload: LogisticsAdvanceIn, user: CurrentUser, db: DbDep
) -> OrderOut:
    order, session = _get_order(db, user, order_id)
    get_owned_session(db, user, session.id)
    if order.logistics_node is None:
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, "订单尚未发货，请先执行发货", 400)
    state_machines.assert_transition(
        state_machines.LOGISTICS_TRANSITIONS, order.logistics_node, payload.node, "物流"
    )
    history = list(order.logistics_history or [])
    history.append({"node": str(payload.node), "at": utcnow().isoformat(), "note": payload.note})
    order.logistics_history = history
    order.logistics_node = payload.node

    if payload.node == LogisticsNode.SIGNED:
        state_machines.assert_transition(
            state_machines.ORDER_TRANSITIONS, order.status, OrderStatus.SIGNED, "订单"
        )
        order.status = OrderStatus.SIGNED
        order.signed_at = utcnow()
    elif payload.node == LogisticsNode.REJECTED:
        # 拒收：订单关闭，商品退回库存（可再次销售）
        state_machines.assert_transition(
            state_machines.ORDER_TRANSITIONS, order.status, OrderStatus.CLOSED, "订单"
        )
        order.status = OrderStatus.CLOSED
        item = db.get(SessionItem, order.item_id)
        if item is not None:
            item.stock += order.qty
    db.commit()
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/close", response_model=OrderOut, summary="关闭订单")
def close_order(order_id: int, user: CurrentUser, db: DbDep) -> OrderOut:
    order, session = _get_order(db, user, order_id)
    get_owned_session(db, user, session.id)
    state_machines.assert_transition(
        state_machines.ORDER_TRANSITIONS, order.status, OrderStatus.CLOSED, "订单"
    )
    order.status = OrderStatus.CLOSED
    db.commit()
    return OrderOut.model_validate(order)
