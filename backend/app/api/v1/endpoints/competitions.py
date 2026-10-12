"""竞赛模块：同场对比与排行榜。

按经营结果形成排行榜，支持 GMV / 利润 / 转化 / 合规 / 互动 / 履约 / 综合分等口径。
"""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core import errors
from app.core.deps import CurrentUser, DbDep, TeacherDep, assert_class_access, get_class_or_404
from app.core.enums import CompetitionMetric, LiveEventType, Role
from app.models.evaluation import Competition
from app.models.live import LiveEvent, Order
from app.models.task import Task, TrainingSession
from app.models.user import User
from app.schemas.evaluation import CompetitionCreateIn, CompetitionOut, LeaderboardOut
from app.services import scoring

router = APIRouter(tags=["竞赛"])


def _violation_count(db: DbDep, session_id: int) -> int:
    return int(
        db.execute(
            select(func.count(LiveEvent.id)).where(
                LiveEvent.session_id == session_id, LiveEvent.type == LiveEventType.VIOLATION
            )
        ).scalar_one()
    )


def _session_metrics(db: DbDep, session: TrainingSession) -> dict:
    m = session.metrics or {}
    orders = int(m.get("orders", 0))
    clicks = int(m.get("item_clicks", 0))
    total_orders = int(
        db.execute(select(func.count(Order.id)).where(Order.session_id == session.id)).scalar_one()
    )
    settled = int(
        db.execute(
            select(func.count(Order.id)).where(
                Order.session_id == session.id, Order.status.in_(["signed", "closed"])
            )
        ).scalar_one()
    )
    violations = _violation_count(db, session.id)
    return {
        "gmv": int(m.get("gmv_cents", 0)),
        "profit": session.fund_balance_cents,
        "conversion": round(orders / clicks, 4) if clicks else 0.0,
        "compliance": max(0.0, 100 - 20 * violations),
        "interaction": int(m.get("likes", 0)) + int(m.get("comments", 0)),
        "fulfillment": round(settled / total_orders, 4) if total_orders else 0.0,
        "orders": orders,
    }


@router.post("/competitions", response_model=CompetitionOut, summary="创建竞赛（教师/管理员）")
def create_competition(payload: CompetitionCreateIn, user: TeacherDep, db: DbDep) -> CompetitionOut:
    klass = get_class_or_404(db, payload.class_id)
    assert_class_access(user, klass)
    if payload.task_id is not None:
        task = db.get(Task, payload.task_id)
        if task is None or task.class_id != klass.id:
            raise errors.validation_error("任务不存在或不属于该班级", {"task_id": payload.task_id})
    comp = Competition(
        class_id=klass.id,
        task_id=payload.task_id,
        name=payload.name,
        metric=str(payload.metric),
        rules=payload.rules,
        status="running",
        created_by=user.id,
    )
    db.add(comp)
    db.commit()
    return CompetitionOut.model_validate(comp)


@router.get("/competitions", response_model=list[CompetitionOut], summary="竞赛列表")
def list_competitions(
    user: CurrentUser, db: DbDep, class_id: int | None = None, status: str | None = None
) -> list[CompetitionOut]:
    stmt = select(Competition)
    if class_id is not None:
        klass = get_class_or_404(db, class_id)
        assert_class_access(user, klass)
        stmt = stmt.where(Competition.class_id == class_id)
    elif user.role == Role.TEACHER:
        from app.models.user import Klass

        class_ids = select(Klass.id).where(Klass.teacher_id == user.id).scalar_subquery()
        stmt = stmt.where(Competition.class_id.in_(class_ids))
    elif user.role == Role.STUDENT:
        stmt = stmt.where(Competition.class_id == user.class_id)
    if status:
        stmt = stmt.where(Competition.status == status)
    rows = db.execute(stmt.order_by(Competition.id.desc())).scalars().all()
    return [CompetitionOut.model_validate(c) for c in rows]


@router.get("/competitions/{competition_id}/leaderboard", response_model=LeaderboardOut, summary="排行榜")
def leaderboard(competition_id: int, user: CurrentUser, db: DbDep) -> LeaderboardOut:
    comp = db.get(Competition, competition_id)
    if comp is None:
        raise errors.not_found("竞赛", competition_id)
    klass = get_class_or_404(db, comp.class_id)
    assert_class_access(user, klass)
    if comp.task_id is not None:
        sessions = list(
            db.execute(
                select(TrainingSession).where(TrainingSession.task_id == comp.task_id)
            ).scalars().all()
        )
    else:
        sessions = list(
            db.execute(
                select(TrainingSession)
                .join(Task, Task.id == TrainingSession.task_id)
                .where(Task.class_id == comp.class_id)
            ).scalars().all()
        )
    owners = {
        u.id: (u.real_name or u.username)
        for u in db.execute(
            select(User).where(User.id.in_([s.owner_id for s in sessions] or [0]))
        ).scalars().all()
    }
    entries: list[dict] = []
    for s in sessions:
        m = _session_metrics(db, s)
        if comp.metric == CompetitionMetric.COMPREHENSIVE:
            value, _ = scoring.compute_objective(db, s)
        else:
            value = m.get(str(comp.metric), 0)
        entries.append(
            {
                "session_id": s.id,
                "owner_id": s.owner_id,
                "owner_name": owners.get(s.owner_id, str(s.owner_id)),
                "session_name": s.name,
                "session_status": s.status,
                "value": value,
                "by_metric": m,
            }
        )
    entries.sort(key=lambda e: e["value"], reverse=True)
    for idx, entry in enumerate(entries, start=1):
        entry["rank"] = idx
    return LeaderboardOut(competition_id=comp.id, metric=comp.metric, entries=entries)


@router.post("/competitions/{competition_id}/close", response_model=CompetitionOut, summary="结束竞赛")
def close_competition(competition_id: int, user: TeacherDep, db: DbDep) -> CompetitionOut:
    comp = db.get(Competition, competition_id)
    if comp is None:
        raise errors.not_found("竞赛", competition_id)
    if user.role != Role.ADMIN and comp.created_by != user.id:
        raise errors.permission_denied("仅竞赛创建教师可结束竞赛")
    comp.status = "closed"
    db.commit()
    return CompetitionOut.model_validate(comp)
