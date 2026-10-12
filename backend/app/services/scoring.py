"""评分服务：客观分（经营/过程/服务/合规/复盘五个维度）+ 综合成绩。

评分保留所采用的权重与评分时间（复查口径一致，题目第 5.4 / 18.11 章）。
各维度 0-100，加权平均得客观分；综合成绩 = 客观分 × 客观占比 + 教师主观分 × (1 - 客观占比)。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.enums import LiveEventType
from app.models.commerce import SessionItem
from app.models.evaluation import Report
from app.models.live import AfterSale, LiveEvent, Order
from app.models.task import Task, TrainingSession
from app.services import preflight

DEFAULT_DIMENSION_WEIGHTS = {
    "operation": 30,  # 经营结果
    "process": 25,  # 过程完成度
    "service": 20,  # 履约与售后
    "compliance": 15,  # 合规表现
    "review": 10,  # 复盘质量
}
DEFAULT_OBJECTIVE_RATIO = 0.6
SERIOUS_VIOLATION_THRESHOLD = 3  # 严重违规约束：达到该次数合规维度直接 0 分


def normalize_weight_config(weight_config: dict | None) -> tuple[dict[str, float], float]:
    cfg = weight_config or {}
    dims = {**DEFAULT_DIMENSION_WEIGHTS, **(cfg.get("dimensions") or {})}
    ratio = float(cfg.get("objective_ratio", DEFAULT_OBJECTIVE_RATIO))
    ratio = min(max(ratio, 0.0), 1.0)
    return dims, ratio


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def compute_objective(db: OrmSession, session: TrainingSession) -> tuple[float, dict]:
    task = db.get(Task, session.task_id)
    initial_fund = task.initial_fund_cents if task else 0
    dims, ratio = normalize_weight_config(task.weight_config if task else None)

    # ---- 经营结果：期末资金 + 库存残值 相对初始资金 ----
    stock_value = int(
        db.execute(
            select(
                func.coalesce(
                    func.sum(SessionItem.stock * func.coalesce(SessionItem.purchase_unit_cost_cents, 0)),
                    0,
                )
            ).where(SessionItem.session_id == session.id)
        ).scalar_one()
    )
    profit_cents = session.fund_balance_cents + stock_value - initial_fund
    ratio_profit = profit_cents / initial_fund if initial_fund else 0.0
    operation_score = _clamp(50 + 50 * ratio_profit)

    # ---- 过程完成度：准备清单通过率 ----
    checklist = preflight.build_checklist(db, session)
    total_items = len(checklist["items"])
    passed_items = sum(1 for i in checklist["items"] if i["passed"])
    process_score = _clamp(100 * passed_items / total_items if total_items else 0)

    # ---- 履约与售后 ----
    total_orders = int(
        db.execute(
            select(func.count(Order.id)).where(Order.session_id == session.id)
        ).scalar_one()
    )
    settled_orders = int(
        db.execute(
            select(func.count(Order.id)).where(
                Order.session_id == session.id, Order.status.in_(["signed", "closed"])
            )
        ).scalar_one()
    )
    total_after_sales = int(
        db.execute(
            select(func.count(AfterSale.id)).where(AfterSale.session_id == session.id)
        ).scalar_one()
    )
    resolved_after_sales = int(
        db.execute(
            select(func.count(AfterSale.id)).where(
                AfterSale.session_id == session.id, AfterSale.status.in_(["approved", "rejected", "closed"])
            )
        ).scalar_one()
    )
    if total_orders:
        fulfil_rate = settled_orders / total_orders
        aftersale_rate = resolved_after_sales / total_after_sales if total_after_sales else 1.0
        service_score = _clamp(100 * (0.7 * fulfil_rate + 0.3 * aftersale_rate))
    else:
        service_score = 70.0  # 无订单时的中性分（避免“不开播反而高分”）

    # ---- 合规 ----
    violations = int(
        db.execute(
            select(func.count(LiveEvent.id)).where(
                LiveEvent.session_id == session.id, LiveEvent.type == LiveEventType.VIOLATION
            )
        ).scalar_one()
    )
    compliance_score = 0.0 if violations >= SERIOUS_VIOLATION_THRESHOLD else _clamp(100 - 20 * violations)

    # ---- 复盘质量 ----
    report = db.execute(
        select(Report).where(Report.session_id == session.id)
    ).scalar_one_or_none()
    review_score = 0.0
    if report is not None:
        review_score += 40.0
        if len((report.improvement_plan or "").strip()) >= 30:
            review_score += 30.0
        if report.status in ("submitted", "scored"):
            review_score += 30.0
    review_score = _clamp(review_score)

    scores = {
        "operation": round(operation_score, 1),
        "process": round(process_score, 1),
        "service": round(service_score, 1),
        "compliance": round(compliance_score, 1),
        "review": round(review_score, 1),
    }
    weight_sum = sum(dims.values()) or 1
    objective = sum(scores[k] * dims.get(k, 0) for k in scores) / weight_sum
    detail = {
        "dimensions": scores,
        "weights": dims,
        "objective_ratio": ratio,
        "evidence": {
            "initial_fund_cents": initial_fund,
            "fund_balance_cents": session.fund_balance_cents,
            "stock_value_cents": stock_value,
            "profit_cents": profit_cents,
            "checklist_passed": f"{passed_items}/{total_items}",
            "orders_settled": f"{settled_orders}/{total_orders}",
            "after_sales_resolved": f"{resolved_after_sales}/{total_after_sales}",
            "violations": violations,
            "report_status": report.status if report else None,
        },
    }
    return round(objective, 1), detail


def comprehensive(objective: float, subjective: float | None, objective_ratio: float) -> float | None:
    if subjective is None:
        return None
    return round(objective * objective_ratio + subjective * (1 - objective_ratio), 1)
