"""售后服务：退款 / 退货 / 换货 / 投诉 / 超卖 / 延迟发货工单。

同意退款会写资金流水（允许余额为负，应退必退）并回补库存；
未完成履约或售后的场次不能提交最终复盘（见 reviews.submit_report）。
"""

from fastapi import APIRouter
from sqlalchemy import select

from app.core import errors
from app.core.deps import CurrentUser, DbDep, assert_session_access, get_owned_session, get_session_or_404
from app.core.enums import AfterSaleStatus, AfterSaleType, FundTxnType, OrderStatus
from app.db.base import utcnow
from app.models.commerce import SessionItem
from app.models.live import AfterSale, Order
from app.schemas.live import (
    AfterSaleCloseIn,
    AfterSaleCreateIn,
    AfterSaleOut,
    AfterSaleResolveIn,
)
from app.services import state_machines

router = APIRouter(tags=["售后服务"])

# 需要退款回补资金与库存的工单类型
REFUND_TYPES = {AfterSaleType.REFUND, AfterSaleType.RETURN, AfterSaleType.OVERSELL, AfterSaleType.DELAY}


@router.get("/sessions/{session_id}/after-sales", response_model=list[AfterSaleOut], summary="售后工单列表")
def list_after_sales(
    session_id: int, user: CurrentUser, db: DbDep, status: AfterSaleStatus | None = None
) -> list[AfterSaleOut]:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    stmt = select(AfterSale).where(AfterSale.session_id == session.id)
    if status is not None:
        stmt = stmt.where(AfterSale.status == status)
    rows = db.execute(stmt.order_by(AfterSale.id.desc())).scalars().all()
    return [AfterSaleOut.model_validate(a) for a in rows]


@router.post("/sessions/{session_id}/after-sales", response_model=AfterSaleOut, summary="创建售后工单")
def create_after_sale(
    session_id: int, payload: AfterSaleCreateIn, user: CurrentUser, db: DbDep
) -> AfterSaleOut:
    session = get_owned_session(db, user, session_id)
    order = db.get(Order, payload.order_id)
    if order is None or order.session_id != session.id:
        raise errors.validation_error("订单不存在或不属于本场次", {"order_id": payload.order_id})
    if order.status == OrderStatus.CLOSED:
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, "已关闭订单不能发起售后", 400)
    default_amount = order.amount_cents if payload.type in REFUND_TYPES else 0
    amount = payload.amount_cents if payload.amount_cents is not None else default_amount
    if amount > order.amount_cents:
        raise errors.validation_error(
            "售后金额不能超过订单金额", {"amount_cents": amount, "order_amount_cents": order.amount_cents}
        )
    after_sale = AfterSale(
        order_id=order.id,
        session_id=session.id,
        type=str(payload.type),
        reason=payload.reason,
        amount_cents=amount,
        status=AfterSaleStatus.PENDING,
    )
    db.add(after_sale)
    db.commit()
    return AfterSaleOut.model_validate(after_sale)


@router.get("/after-sales/{after_sale_id}", response_model=AfterSaleOut, summary="售后工单详情")
def get_after_sale(after_sale_id: int, user: CurrentUser, db: DbDep) -> AfterSaleOut:
    after_sale = db.get(AfterSale, after_sale_id)
    if after_sale is None:
        raise errors.not_found("售后工单", after_sale_id)
    session = get_session_or_404(db, after_sale.session_id)
    assert_session_access(db, user, session)
    return AfterSaleOut.model_validate(after_sale)


@router.post("/after-sales/{after_sale_id}/resolve", response_model=AfterSaleOut, summary="同意/驳回售后")
def resolve_after_sale(
    after_sale_id: int, payload: AfterSaleResolveIn, user: CurrentUser, db: DbDep
) -> AfterSaleOut:
    from app.services import fund

    after_sale = db.get(AfterSale, after_sale_id)
    if after_sale is None:
        raise errors.not_found("售后工单", after_sale_id)
    session = get_owned_session(db, user, after_sale.session_id)
    target = AfterSaleStatus.APPROVED if payload.action == "approve" else AfterSaleStatus.REJECTED
    state_machines.assert_transition(
        state_machines.AFTER_SALE_TRANSITIONS, after_sale.status, target, "售后工单"
    )
    after_sale.status = target
    after_sale.handler_id = user.id
    after_sale.handler_note = payload.note
    after_sale.resolved_at = utcnow()

    if target == AfterSaleStatus.APPROVED:
        order = db.get(Order, after_sale.order_id)
        if order is not None and after_sale.type in REFUND_TYPES and after_sale.amount_cents > 0:
            fund.apply_fund_txn(
                db,
                session,
                FundTxnType.REFUND,
                -after_sale.amount_cents,
                ref_type="after_sale",
                ref_id=after_sale.id,
                note=f"售后退款（{after_sale.type}）",
                allow_negative=True,  # 应退必退，允许余额为负
            )
        if order is not None and after_sale.type in (
            AfterSaleType.REFUND,
            AfterSaleType.RETURN,
            AfterSaleType.OVERSELL,
        ):
            # 退货/退款/超卖：商品回到库存
            item = db.get(SessionItem, order.item_id)
            if item is not None:
                item.stock += order.qty
            if order.status != OrderStatus.CLOSED:
                order.status = OrderStatus.CLOSED
    db.commit()
    return AfterSaleOut.model_validate(after_sale)


@router.post("/after-sales/{after_sale_id}/close", response_model=AfterSaleOut, summary="结案")
def close_after_sale(
    after_sale_id: int, payload: AfterSaleCloseIn, user: CurrentUser, db: DbDep
) -> AfterSaleOut:
    after_sale = db.get(AfterSale, after_sale_id)
    if after_sale is None:
        raise errors.not_found("售后工单", after_sale_id)
    get_owned_session(db, user, after_sale.session_id)
    state_machines.assert_transition(
        state_machines.AFTER_SALE_TRANSITIONS, after_sale.status, AfterSaleStatus.CLOSED, "售后工单"
    )
    after_sale.status = AfterSaleStatus.CLOSED
    if payload.note:
        after_sale.handler_note = (after_sale.handler_note + "\n" + payload.note).strip()
    db.commit()
    return AfterSaleOut.model_validate(after_sale)
