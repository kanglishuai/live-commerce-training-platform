"""数据复盘与学习评价：数据罗盘、复盘报告生成/提交/退回、教师评分、班级报告与巡课。

硬约束：
- 未完成履约或售后的场次不能提交最终复盘（FULFILLMENT_INCOMPLETE）。
- 复盘提交后锁定（只读）；教师可退回，退回后可修改再提交。
- AI 报告与规则兜底以 source 字段区分（llm / rule）。
"""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core import errors
from app.core.deps import (
    CurrentUser,
    DbDep,
    assert_class_access,
    assert_session_access,
    get_class_or_404,
    get_owned_session,
    get_session_or_404,
)
from app.core.enums import LiveEventType, OrderStatus, ReportStatus, Role, SessionStatus
from app.db.base import utcnow
from app.models.evaluation import Report, Score
from app.models.live import AfterSale, LiveEvent, Order
from app.models.task import Task, TrainingSession
from app.models.user import User
from app.schemas.evaluation import (
    ClassReportOut,
    MetricsOut,
    PatrolOut,
    ReportOut,
    ReportReturnIn,
    ReportUpdateIn,
    ScoreIn,
    ScoreOut,
)
from app.services import metrics as metrics_service
from app.services import reporting, scoring, state_machines

router = APIRouter(tags=["复盘与评价"])

VIEWS = ("overview", "sales", "traffic", "users")


# ---- 数据罗盘 ----

@router.get("/sessions/{session_id}/metrics", response_model=MetricsOut, summary="数据罗盘")
def get_metrics(
    session_id: int, user: CurrentUser, db: DbDep, view: str = Query("overview")
) -> MetricsOut:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    if view not in VIEWS:
        raise errors.validation_error(f"未知视角 {view}", {"allowed": list(VIEWS)})
    data, notes = metrics_service.build(db, session, view)
    return MetricsOut(session_id=session.id, view=view, data=data, notes=notes)


# ---- 复盘报告 ----

def _get_report(db: DbDep, session_id: int) -> Report | None:
    return db.execute(select(Report).where(Report.session_id == session_id)).scalar_one_or_none()


@router.post("/sessions/{session_id}/report/generate", response_model=ReportOut, summary="生成/重新生成复盘报告")
def generate_report(session_id: int, user: CurrentUser, db: DbDep) -> ReportOut:
    session = get_owned_session(db, user, session_id)
    if session.status == SessionStatus.PREPARING:
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, "尚未开播，无法生成复盘报告", 400)
    report = _get_report(db, session.id)
    if report is not None and report.locked:
        raise errors.AppError(errors.REPORT_LOCKED, "报告已提交锁定，不能重新生成", 400)
    report = reporting.generate(db, session)
    db.commit()
    return ReportOut.model_validate(report)


@router.get("/sessions/{session_id}/report", response_model=ReportOut, summary="读取复盘报告")
def get_report(session_id: int, user: CurrentUser, db: DbDep) -> ReportOut:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    report = _get_report(db, session.id)
    if report is None:
        raise errors.not_found("复盘报告（请先生成）", session_id)
    return ReportOut.model_validate(report)


@router.put("/sessions/{session_id}/report", response_model=ReportOut, summary="填写改进措施（草稿）")
def update_report(session_id: int, payload: ReportUpdateIn, user: CurrentUser, db: DbDep) -> ReportOut:
    session = get_owned_session(db, user, session_id)
    report = _get_report(db, session.id)
    if report is None:
        raise errors.not_found("复盘报告（请先生成）", session_id)
    if report.locked:
        raise errors.AppError(errors.REPORT_LOCKED, "报告已提交锁定，不能修改", 400)
    report.improvement_plan = payload.improvement_plan
    db.commit()
    return ReportOut.model_validate(report)


@router.post("/sessions/{session_id}/report/submit", response_model=ReportOut, summary="提交复盘（锁定）")
def submit_report(session_id: int, user: CurrentUser, db: DbDep) -> ReportOut:
    session = get_owned_session(db, user, session_id)
    report = _get_report(db, session.id)
    if report is None:
        raise errors.not_found("复盘报告（请先生成）", session_id)
    if report.locked:
        raise errors.AppError(errors.REPORT_LOCKED, "报告已提交锁定", 400)

    pending_orders = int(
        db.execute(
            select(func.count(Order.id)).where(
                Order.session_id == session.id,
                Order.status.in_([OrderStatus.PENDING_SHIP, OrderStatus.SHIPPING]),
            )
        ).scalar_one()
    )
    pending_after_sales = int(
        db.execute(
            select(func.count(AfterSale.id)).where(
                AfterSale.session_id == session.id, AfterSale.status == "pending"
            )
        ).scalar_one()
    )
    if pending_orders or pending_after_sales:
        raise errors.AppError(
            errors.FULFILLMENT_INCOMPLETE,
            f"还有 {pending_orders} 笔订单未完成履约、{pending_after_sales} 笔售后未处理，不能提交复盘",
            400,
            {"pending_orders": pending_orders, "pending_after_sales": pending_after_sales},
        )

    if session.status == SessionStatus.ENDED:
        state_machines.assert_transition(
            state_machines.SESSION_TRANSITIONS, session.status, SessionStatus.SUBMITTED, "场次"
        )
    elif session.status == SessionStatus.SUBMITTED and report.status == ReportStatus.RETURNED:
        pass  # 退回后重新提交
    else:
        raise errors.AppError(
            errors.STATE_TRANSITION_INVALID,
            f"当前场次状态 {session.status} / 报告状态 {report.status} 不能提交复盘",
            400,
        )

    report.status = ReportStatus.SUBMITTED
    report.locked = True
    report.submitted_at = utcnow()
    session.status = SessionStatus.SUBMITTED
    session.submitted_at = utcnow()
    db.commit()
    return ReportOut.model_validate(report)


@router.post("/sessions/{session_id}/report/return", response_model=ReportOut, summary="退回复盘（教师）")
def return_report(
    session_id: int, payload: ReportReturnIn, user: CurrentUser, db: DbDep
) -> ReportOut:
    session = get_session_or_404(db, session_id)
    if user.role == Role.STUDENT:
        raise errors.permission_denied("仅教师可退回复盘")
    assert_session_access(db, user, session)
    report = _get_report(db, session.id)
    if report is None or report.status not in (ReportStatus.SUBMITTED, ReportStatus.SCORED):
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, "只有已提交的报告可以退回", 400)
    state_machines.assert_transition(
        state_machines.SESSION_TRANSITIONS, session.status, SessionStatus.ENDED, "场次"
    )
    report.status = ReportStatus.RETURNED
    report.locked = False
    report.returned_reason = payload.reason
    session.status = SessionStatus.ENDED
    db.commit()
    return ReportOut.model_validate(report)


# ---- 评分 ----

@router.post("/sessions/{session_id}/score", response_model=ScoreOut, summary="教师评分（主观分并入综合成绩）")
def score_session(session_id: int, payload: ScoreIn, user: CurrentUser, db: DbDep) -> ScoreOut:
    session = get_session_or_404(db, session_id)
    if user.role == Role.STUDENT:
        raise errors.permission_denied("仅教师可评分")
    assert_session_access(db, user, session)
    report = _get_report(db, session.id)
    if report is None or report.status not in (ReportStatus.SUBMITTED, ReportStatus.SCORED):
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, "学生尚未提交复盘，不能评分", 400)

    objective, detail = scoring.compute_objective(db, session)
    score = db.execute(select(Score).where(Score.session_id == session.id)).scalar_one_or_none()
    if score is None:
        score = Score(session_id=session.id)
        db.add(score)
    score.objective_score = objective
    score.objective_detail = detail
    score.subjective_score = payload.subjective_score
    score.comprehensive_score = scoring.comprehensive(
        objective, payload.subjective_score, detail["objective_ratio"]
    )
    score.comment = payload.comment
    score.weights = detail["weights"]
    score.teacher_id = user.id
    score.scored_at = utcnow()
    if report.status == ReportStatus.SUBMITTED:
        report.status = ReportStatus.SCORED
    db.commit()
    return ScoreOut.model_validate(score)


@router.get("/sessions/{session_id}/score", response_model=ScoreOut, summary="读取成绩")
def get_score(session_id: int, user: CurrentUser, db: DbDep) -> ScoreOut:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    score = db.execute(select(Score).where(Score.session_id == session.id)).scalar_one_or_none()
    if score is None:
        raise errors.not_found("成绩（尚未评分）", session_id)
    return ScoreOut.model_validate(score)


# ---- 班级报告与巡课 ----

def _class_sessions(db: DbDep, class_id: int, task_id: int | None = None) -> list[TrainingSession]:
    stmt = (
        select(TrainingSession)
        .join(Task, Task.id == TrainingSession.task_id)
        .where(Task.class_id == class_id)
    )
    if task_id is not None:
        stmt = stmt.where(TrainingSession.task_id == task_id)
    return list(db.execute(stmt.order_by(TrainingSession.id)).scalars().all())


@router.get("/classes/{class_id}/report", response_model=ClassReportOut, summary="班级报告")
def class_report(
    class_id: int, user: CurrentUser, db: DbDep, task_id: int | None = None
) -> ClassReportOut:
    klass = get_class_or_404(db, class_id)
    assert_class_access(user, klass)
    sessions = _class_sessions(db, class_id, task_id)
    scores = {
        s.session_id: s
        for s in db.execute(
            select(Score).where(Score.session_id.in_([x.id for x in sessions] or [0]))
        ).scalars().all()
    }
    reports = {
        r.session_id: r
        for r in db.execute(
            select(Report).where(Report.session_id.in_([x.id for x in sessions] or [0]))
        ).scalars().all()
    }
    students = {
        u.id: u
        for u in db.execute(select(User).where(User.class_id == class_id)).scalars().all()
    }
    rows: list[dict] = []
    for s in sessions:
        owner = students.get(s.owner_id)
        score = scores.get(s.id)
        report = reports.get(s.id)
        rows.append(
            {
                "session_id": s.id,
                "student_id": s.owner_id,
                "student_name": (owner.real_name or owner.username) if owner else str(s.owner_id),
                "status": s.status,
                "gmv_cents": int((s.metrics or {}).get("gmv_cents", 0)),
                "orders": int((s.metrics or {}).get("orders", 0)),
                "report_status": report.status if report else None,
                "objective_score": score.objective_score if score else None,
                "subjective_score": score.subjective_score if score else None,
                "comprehensive_score": score.comprehensive_score if score else None,
            }
        )
    submitted = sum(1 for r in rows if r["comprehensive_score"] is not None)
    summary = {
        "task_id": task_id,
        "sessions": len(rows),
        "students_participated": len({r["student_id"] for r in rows}),
        "submitted_scored": submitted,
        "gmv_cents_total": sum(r["gmv_cents"] for r in rows),
        "avg_comprehensive": (
            round(sum(r["comprehensive_score"] for r in rows if r["comprehensive_score"]) / submitted, 1)
            if submitted
            else None
        ),
        "export": "导出功能规划中（占位）",
    }
    return ClassReportOut(class_id=class_id, class_name=klass.name, summary=summary, students=rows)


@router.get("/classes/{class_id}/patrol", response_model=PatrolOut, summary="巡课工作台")
def patrol(class_id: int, user: CurrentUser, db: DbDep, task_id: int | None = None) -> PatrolOut:
    klass = get_class_or_404(db, class_id)
    assert_class_access(user, klass)
    sessions = _class_sessions(db, class_id, task_id)
    students = {
        u.id: u
        for u in db.execute(select(User).where(User.class_id == class_id)).scalars().all()
    }
    groups: list[dict] = []
    for s in sessions:
        latest_comments = db.execute(
            select(LiveEvent)
            .where(LiveEvent.session_id == s.id, LiveEvent.type == LiveEventType.COMMENT)
            .order_by(LiveEvent.id.desc())
            .limit(3)
        ).scalars().all()
        owner = students.get(s.owner_id)
        groups.append(
            {
                "session_id": s.id,
                "title": s.name,
                "owner_id": s.owner_id,
                "owner_name": (owner.real_name or owner.username) if owner else str(s.owner_id),
                "status": s.status,
                "metrics": {
                    "online": int((s.metrics or {}).get("online", 0)),
                    "viewers": int((s.metrics or {}).get("viewers", 0)),
                    "orders": int((s.metrics or {}).get("orders", 0)),
                    "gmv_cents": int((s.metrics or {}).get("gmv_cents", 0)),
                },
                "latest_comments": [(e.payload or {}).get("text", "") for e in latest_comments],
                "prep_progress": "已开播" if s.started_at else ("准备中" if s.status == "preparing" else s.status),
            }
        )
    return PatrolOut(class_id=class_id, groups=groups)
