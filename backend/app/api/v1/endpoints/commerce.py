"""经营准备中的商务环节：货盘、采购、资金流水、促销、投流。

资金相关操作统一经 services/fund.apply_fund_txn（余额不足显式报错）。
直播中与提交复盘后不允许修改经营准备数据（直播中上下架走中控动作）。
"""

from fastapi import APIRouter

from app.core import errors
from app.core.deps import CurrentUser, DbDep, get_owned_session, get_session_or_404, assert_session_access
from app.core.enums import AdStatus, FundTxnType, ItemStatus, SessionStatus
from app.models.commerce import AdPlan, FundTxn, Product, Promotion, Purchase, SessionItem
from app.models.task import TrainingSession
from app.schemas.commerce import (
    AdPlanIn,
    AdPlanOut,
    AdPlanStatusIn,
    CartAddIn,
    CartItemOut,
    CartItemPatchIn,
    CartOut,
    CustomItemIn,
    FundTxnOut,
    PricingIn,
    PromotionIn,
    PromotionOut,
    PromotionPatchIn,
    PurchaseIn,
    PurchaseOut,
    PurchaseResultOut,
)
from sqlalchemy import func, select

router = APIRouter(tags=["货盘与经营"])


def _assert_prep_editable(session: TrainingSession) -> None:
    if session.status in (SessionStatus.LIVE, SessionStatus.PAUSED):
        raise errors.AppError(
            errors.STATE_TRANSITION_INVALID,
            "直播中不能修改经营准备数据（上下架请在直播中控执行）",
            400,
            {"current": session.status},
        )
    if session.status == SessionStatus.SUBMITTED:
        raise errors.AppError(errors.REPORT_LOCKED, "复盘已提交，相关业务记录已锁定", 400)


def _cart_item_out(db: DbDep, item: SessionItem) -> CartItemOut:
    product = db.get(Product, item.product_id) if item.product_id else None
    return CartItemOut(
        id=item.id,
        session_id=item.session_id,
        product_id=item.product_id,
        name=(item.title or (product.name if product else "") or item.custom_name or ""),
        role=item.role,
        status=item.status,
        title=item.title,
        tags=item.tags or [],
        images=item.images or [],
        selling_points=item.selling_points or [],
        detail=item.detail,
        list_price_cents=item.list_price_cents,
        live_price_cents=item.live_price_cents,
        stock=item.stock,
        purchased_qty=item.purchased_qty,
        purchase_unit_cost_cents=item.purchase_unit_cost_cents,
        cost_cents=(
            item.purchase_unit_cost_cents
            if item.purchase_unit_cost_cents is not None
            else (product.cost_cents if product else (item.custom_cost_cents or 0))
        ),
        market_price_cents=(product.market_price_cents if product else 0),
        sort=item.sort,
    )


def _get_item(db: DbDep, session: TrainingSession, item_id: int) -> SessionItem:
    item = db.get(SessionItem, item_id)
    if item is None or item.session_id != session.id:
        raise errors.not_found("货盘商品", item_id)
    return item


# ---- 货盘 ----

@router.get("/sessions/{session_id}/cart", response_model=CartOut, summary="货盘视图")
def get_cart(session_id: int, user: CurrentUser, db: DbDep) -> CartOut:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    items = db.execute(
        select(SessionItem).where(SessionItem.session_id == session.id).order_by(SessionItem.sort, SessionItem.id)
    ).scalars().all()
    total_cost = int(
        db.execute(
            select(func.coalesce(func.sum(Purchase.total_cents), 0)).where(
                Purchase.session_id == session.id
            )
        ).scalar_one()
    )
    return CartOut(
        session_id=session.id,
        fund_balance_cents=session.fund_balance_cents,
        total_cost_cents=total_cost,
        items=[_cart_item_out(db, i) for i in items],
    )


@router.post("/sessions/{session_id}/cart/items", response_model=CartItemOut, summary="加入货盘")
def add_cart_item(session_id: int, payload: CartAddIn, user: CurrentUser, db: DbDep) -> CartItemOut:
    session = get_owned_session(db, user, session_id)
    _assert_prep_editable(session)
    product = db.get(Product, payload.product_id)
    if product is None or product.status != "on":
        raise errors.validation_error("商品不存在或已下架", {"product_id": payload.product_id})
    dup = db.execute(
        select(SessionItem.id).where(
            SessionItem.session_id == session.id, SessionItem.product_id == product.id
        )
    ).first()
    if dup:
        raise errors.AppError(errors.DUPLICATE, "该商品已在货盘中", 409)
    next_sort = len(
        db.execute(select(SessionItem.id).where(SessionItem.session_id == session.id)).all()
    )
    item = SessionItem(
        session_id=session.id,
        product_id=product.id,
        role=str(payload.role),
        title=product.name,
        images=list(product.images or []),
        selling_points=list(product.selling_points or []),
        detail=product.description,
        list_price_cents=product.market_price_cents,
        stock=0,
        sort=next_sort,
    )
    db.add(item)
    db.commit()
    return _cart_item_out(db, item)


@router.post("/sessions/{session_id}/cart/custom-items", response_model=CartItemOut, summary="添加自定义商品")
def add_custom_item(
    session_id: int, payload: CustomItemIn, user: CurrentUser, db: DbDep
) -> CartItemOut:
    session = get_owned_session(db, user, session_id)
    _assert_prep_editable(session)
    next_sort = len(
        db.execute(select(SessionItem.id).where(SessionItem.session_id == session.id)).all()
    )
    item = SessionItem(
        session_id=session.id,
        product_id=None,
        custom_name=payload.name,
        custom_cost_cents=payload.cost_cents,
        role=str(payload.role),
        title=payload.name,
        images=list(payload.images),
        selling_points=list(payload.selling_points),
        detail=payload.description,
        list_price_cents=payload.market_price_cents,
        stock=0,
        sort=next_sort,
    )
    db.add(item)
    db.commit()
    return _cart_item_out(db, item)


@router.patch("/sessions/{session_id}/cart/items/{item_id}", response_model=CartItemOut, summary="维护货盘商品图文")
def patch_cart_item(
    session_id: int, item_id: int, payload: CartItemPatchIn, user: CurrentUser, db: DbDep
) -> CartItemOut:
    session = get_owned_session(db, user, session_id)
    _assert_prep_editable(session)
    item = _get_item(db, session, item_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(item, key, str(value) if key == "status" and value is not None else value)
    db.commit()
    return _cart_item_out(db, item)


@router.delete("/sessions/{session_id}/cart/items/{item_id}", summary="移出货盘")
def delete_cart_item(session_id: int, item_id: int, user: CurrentUser, db: DbDep) -> dict:
    session = get_owned_session(db, user, session_id)
    _assert_prep_editable(session)
    item = _get_item(db, session, item_id)
    if item.purchased_qty > 0:
        raise errors.AppError(
            errors.STATE_TRANSITION_INVALID, "该商品已有采购记录，不能直接移除（可改为下架）", 400
        )
    db.delete(item)
    db.commit()
    return {"ok": True, "detail": f"货盘商品 {item_id} 已移除"}


@router.put(
    "/sessions/{session_id}/cart/items/{item_id}/pricing",
    response_model=CartItemOut,
    summary="设置划线价/直播价/库存",
)
def set_pricing(
    session_id: int, item_id: int, payload: PricingIn, user: CurrentUser, db: DbDep
) -> CartItemOut:
    session = get_owned_session(db, user, session_id)
    _assert_prep_editable(session)
    item = _get_item(db, session, item_id)
    item.list_price_cents = payload.list_price_cents
    item.live_price_cents = payload.live_price_cents
    item.stock = payload.stock
    if payload.stock > 0 and item.status == ItemStatus.EDITING:
        item.status = ItemStatus.LISTED
    db.commit()
    return _cart_item_out(db, item)


# ---- 采购 ----

@router.post("/sessions/{session_id}/purchases", response_model=PurchaseResultOut, summary="采购下单")
def create_purchase(
    session_id: int, payload: PurchaseIn, user: CurrentUser, db: DbDep
) -> PurchaseResultOut:
    from app.services import fund

    get_owned_session(db, user, session_id)  # 权限校验（归属人/同队成员）
    session = fund.lock_session(db, session_id)  # 行锁；资金扣减前取余额
    _assert_prep_editable(session)

    item = _get_item(db, session, payload.item_id)
    product = db.get(Product, item.product_id) if item.product_id else None
    unit_cost = payload.unit_cost_cents
    if unit_cost is None:
        unit_cost = (
            product.cost_cents if product else (item.custom_cost_cents or 0)
        )
    total = unit_cost * payload.qty
    txn_note = f"采购 {item.title or item.custom_name} × {payload.qty}"
    purchase = Purchase(
        session_id=session.id,
        item_id=item.id,
        supplier=payload.supplier,
        qty=payload.qty,
        unit_cost_cents=unit_cost,
        total_cents=total,
    )
    db.add(purchase)
    db.flush()
    fund.apply_fund_txn(
        db,
        session,
        FundTxnType.PURCHASE,
        -total,
        ref_type="purchase",
        ref_id=purchase.id,
        note=txn_note,
    )
    item.purchased_qty += payload.qty
    item.purchase_unit_cost_cents = unit_cost
    item.stock += payload.qty
    if item.live_price_cents == 0:
        item.live_price_cents = max(unit_cost, 1)
    db.commit()
    return PurchaseResultOut(
        purchase=PurchaseOut.model_validate(purchase),
        fund_balance_cents=session.fund_balance_cents,
    )


@router.get("/sessions/{session_id}/purchases", response_model=list[PurchaseOut], summary="采购记录")
def list_purchases(session_id: int, user: CurrentUser, db: DbDep) -> list[PurchaseOut]:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    rows = db.execute(
        select(Purchase).where(Purchase.session_id == session.id).order_by(Purchase.id)
    ).scalars().all()
    return [PurchaseOut.model_validate(p) for p in rows]


@router.get("/sessions/{session_id}/fund-txns", response_model=list[FundTxnOut], summary="资金流水")
def list_fund_txns(session_id: int, user: CurrentUser, db: DbDep) -> list[FundTxnOut]:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    rows = db.execute(
        select(FundTxn).where(FundTxn.session_id == session.id).order_by(FundTxn.id)
    ).scalars().all()
    return [FundTxnOut.model_validate(t) for t in rows]


# ---- 促销 ----

@router.post("/sessions/{session_id}/promotions", response_model=PromotionOut, summary="配置促销")
def create_promotion(
    session_id: int, payload: PromotionIn, user: CurrentUser, db: DbDep
) -> PromotionOut:
    session = get_owned_session(db, user, session_id)
    _assert_prep_editable(session)
    promo = Promotion(
        session_id=session.id,
        type=str(payload.type),
        config=payload.config,
        budget_cents=payload.budget_cents,
    )
    db.add(promo)
    db.commit()
    return PromotionOut.model_validate(promo)


@router.get("/sessions/{session_id}/promotions", response_model=list[PromotionOut], summary="促销列表")
def list_promotions(session_id: int, user: CurrentUser, db: DbDep) -> list[PromotionOut]:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    rows = db.execute(
        select(Promotion).where(Promotion.session_id == session.id).order_by(Promotion.id)
    ).scalars().all()
    return [PromotionOut.model_validate(p) for p in rows]


@router.patch("/promotions/{promotion_id}", response_model=PromotionOut, summary="启停促销")
def patch_promotion(
    promotion_id: int, payload: PromotionPatchIn, user: CurrentUser, db: DbDep
) -> PromotionOut:
    promo = db.get(Promotion, promotion_id)
    if promo is None:
        raise errors.not_found("促销", promotion_id)
    get_owned_session(db, user, promo.session_id)
    promo.status = str(payload.status)
    db.commit()
    return PromotionOut.model_validate(promo)


@router.delete("/promotions/{promotion_id}", summary="删除促销")
def delete_promotion(promotion_id: int, user: CurrentUser, db: DbDep) -> dict:
    promo = db.get(Promotion, promotion_id)
    if promo is None:
        raise errors.not_found("促销", promotion_id)
    get_owned_session(db, user, promo.session_id)
    db.delete(promo)
    db.commit()
    return {"ok": True, "detail": f"促销 {promotion_id} 已删除"}


# ---- 投流 ----

@router.post("/sessions/{session_id}/ad-plans", response_model=AdPlanOut, summary="创建投流计划")
def create_ad_plan(session_id: int, payload: AdPlanIn, user: CurrentUser, db: DbDep) -> AdPlanOut:
    session = get_owned_session(db, user, session_id)
    _assert_prep_editable(session)
    plan = AdPlan(
        session_id=session.id,
        channel=str(payload.channel),
        objective=str(payload.objective),
        budget_cents=payload.budget_cents,
        audience=payload.audience,
        creative=payload.creative,
        bid_cents=payload.bid_cents,
    )
    db.add(plan)
    db.commit()
    return AdPlanOut.model_validate(plan)


@router.get("/sessions/{session_id}/ad-plans", response_model=list[AdPlanOut], summary="投流计划列表")
def list_ad_plans(session_id: int, user: CurrentUser, db: DbDep) -> list[AdPlanOut]:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    rows = db.execute(
        select(AdPlan).where(AdPlan.session_id == session.id).order_by(AdPlan.id)
    ).scalars().all()
    return [AdPlanOut.model_validate(p) for p in rows]


@router.post("/ad-plans/{plan_id}/activate", response_model=AdPlanOut, summary="启用投流计划")
def activate_ad_plan(plan_id: int, user: CurrentUser, db: DbDep) -> AdPlanOut:
    plan = db.get(AdPlan, plan_id)
    if plan is None:
        raise errors.not_found("投流计划", plan_id)
    session = get_owned_session(db, user, plan.session_id)
    _assert_prep_editable(session)
    if plan.spent_cents >= plan.budget_cents:
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, "预算已耗尽，无法启用", 400)
    plan.status = str(AdStatus.ACTIVE)
    db.commit()
    return AdPlanOut.model_validate(plan)


@router.post("/ad-plans/{plan_id}/stop", response_model=AdPlanOut, summary="停止投流计划")
def stop_ad_plan(plan_id: int, user: CurrentUser, db: DbDep) -> AdPlanOut:
    plan = db.get(AdPlan, plan_id)
    if plan is None:
        raise errors.not_found("投流计划", plan_id)
    get_owned_session(db, user, plan.session_id)
    plan.status = str(AdStatus.STOPPED)
    db.commit()
    return AdPlanOut.model_validate(plan)


@router.delete("/ad-plans/{plan_id}", summary="删除投流计划")
def delete_ad_plan(plan_id: int, user: CurrentUser, db: DbDep) -> dict:
    plan = db.get(AdPlan, plan_id)
    if plan is None:
        raise errors.not_found("投流计划", plan_id)
    get_owned_session(db, user, plan.session_id)
    if plan.spent_cents > 0:
        raise errors.AppError(
            errors.STATE_TRANSITION_INVALID, "已有消耗的投流计划不能删除（可停止）", 400
        )
    db.delete(plan)
    db.commit()
    return {"ok": True, "detail": f"投流计划 {plan_id} 已删除"}
