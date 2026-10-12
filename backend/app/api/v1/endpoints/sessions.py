"""场次与经营准备：创建场次、调研 / 策划 / 脚本 / 装修、开播检查。

场次是全部业务数据的归属核心；写入类接口仅允许场次归属人（含同队成员）。
"""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core import errors
from app.core.deps import (
    CurrentUser,
    DbDep,
    assert_session_access,
    assert_task_access,
    get_owned_session,
    get_session_or_404,
    get_task_or_404,
)
from app.core.enums import Role, SessionStatus, TaskStatus
from app.models.task import Task, TrainingSession
from app.models.user import Klass, Team, TeamMember
from app.schemas.common import Page
from app.schemas.task import (
    PlanIn,
    PreflightOut,
    ResearchIn,
    RoomCopyIn,
    RoomIn,
    ScriptIn,
    SessionCreateIn,
    SessionOut,
    TaskOut,
)

router = APIRouter(tags=["场次与经营准备"])


@router.post("/tasks/{task_id}/sessions", response_model=SessionOut, summary="创建训练场次（学生）")
def create_session(
    task_id: int, payload: SessionCreateIn, user: CurrentUser, db: DbDep
) -> SessionOut:
    task = get_task_or_404(db, task_id)
    assert_task_access(user, task)
    if user.role != Role.ADMIN and task.status != TaskStatus.PUBLISHED:
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, "只有已发布的任务可以创建场次", 400)
    if user.role == Role.STUDENT and user.class_id != task.class_id:
        raise errors.permission_denied("该任务不属于你所在班级")

    team_id = payload.team_id
    if team_id is not None:
        team = db.get(Team, team_id)
        if team is None or team.class_id != task.class_id:
            raise errors.validation_error("团队不存在或不属于任务班级", {"team_id": team_id})
        if user.role == Role.STUDENT:
            member = db.execute(
                select(TeamMember.id).where(
                    TeamMember.team_id == team_id, TeamMember.user_id == user.id
                )
            ).first()
            if not member:
                raise errors.permission_denied("你不是该团队成员")

    seq = db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.task_id == task.id, TrainingSession.owner_id == user.id
        )
    ).scalar_one()
    session = TrainingSession(
        task_id=task.id,
        owner_id=user.id,
        team_id=team_id,
        name=payload.name or f"{user.real_name or user.username} 第{int(seq) + 1}场",
        status=str(SessionStatus.PREPARING),
        fund_balance_cents=task.initial_fund_cents,
        metrics={},
    )
    db.add(session)
    db.commit()
    return SessionOut.model_validate(session)


@router.get("/sessions", response_model=Page[SessionOut], summary="场次列表（按角色范围）")
def list_sessions(
    user: CurrentUser,
    db: DbDep,
    task_id: int | None = None,
    status: SessionStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[SessionOut]:
    stmt, count_stmt = select(TrainingSession), select(func.count(TrainingSession.id))
    if user.role == Role.STUDENT:
        cond = TrainingSession.owner_id == user.id
    else:
        teacher_class_ids = select(Klass.id).where(Klass.teacher_id == user.id).scalar_subquery()
        teacher_task_ids = select(Task.id).where(Task.class_id.in_(teacher_class_ids)).scalar_subquery()
        cond = TrainingSession.task_id.in_(teacher_task_ids) if user.role == Role.TEACHER else None
    if cond is not None:
        stmt, count_stmt = stmt.where(cond), count_stmt.where(cond)
    if task_id is not None:
        stmt, count_stmt = stmt.where(TrainingSession.task_id == task_id), count_stmt.where(TrainingSession.task_id == task_id)
    if status is not None:
        stmt, count_stmt = stmt.where(TrainingSession.status == status), count_stmt.where(TrainingSession.status == status)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(TrainingSession.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[SessionOut](
        items=[SessionOut.model_validate(s) for s in rows], total=total, page=page, page_size=page_size
    )


@router.get("/sessions/{session_id}", response_model=SessionOut, summary="场次详情")
def get_session(session_id: int, user: CurrentUser, db: DbDep) -> SessionOut:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    return SessionOut.model_validate(session)


@router.get("/sessions/{session_id}/task", response_model=TaskOut, summary="场次关联的任务")
def get_session_task(session_id: int, user: CurrentUser, db: DbDep) -> TaskOut:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    return TaskOut.model_validate(get_task_or_404(db, session.task_id))


# ---- 经营准备各环节 ----

@router.put("/sessions/{session_id}/research", response_model=SessionOut, summary="保存调研纪要")
def save_research(session_id: int, payload: ResearchIn, user: CurrentUser, db: DbDep) -> SessionOut:
    session = get_owned_session(db, user, session_id)
    session.research = payload.model_dump()
    db.commit()
    return SessionOut.model_validate(session)


@router.put("/sessions/{session_id}/plan", response_model=SessionOut, summary="保存直播策划")
def save_plan(session_id: int, payload: PlanIn, user: CurrentUser, db: DbDep) -> SessionOut:
    from app.models.commerce import SessionItem

    session = get_owned_session(db, user, session_id)
    data = payload.model_dump()
    for item_id in data.get("main_items") or []:
        item = db.get(SessionItem, item_id)
        if item is None or item.session_id != session.id:
            raise errors.validation_error("main_items 含无效商品", {"item_id": item_id})
    session.plan = data
    db.commit()
    return SessionOut.model_validate(session)


@router.get("/sessions/{session_id}/script", summary="读取直播脚本")
def get_script(session_id: int, user: CurrentUser, db: DbDep) -> dict:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    return session.script or {"segments": [], "adopted_notes": []}


@router.put("/sessions/{session_id}/script", summary="保存直播脚本")
def save_script(session_id: int, payload: ScriptIn, user: CurrentUser, db: DbDep) -> dict:
    session = get_owned_session(db, user, session_id)
    existing = session.script or {}
    session.script = {
        "segments": [s.model_dump() for s in payload.segments],
        "adopted_notes": existing.get("adopted_notes", []),
    }
    db.commit()
    return session.script


@router.get("/sessions/{session_id}/room", summary="读取直播间装修")
def get_room(session_id: int, user: CurrentUser, db: DbDep) -> dict:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    return session.room_config or {}


@router.put("/sessions/{session_id}/room", summary="保存直播间装修")
def save_room(session_id: int, payload: RoomIn, user: CurrentUser, db: DbDep) -> dict:
    session = get_owned_session(db, user, session_id)
    session.room_config = payload.model_dump(mode="json")
    db.commit()
    return session.room_config


@router.post("/sessions/{session_id}/room/copy", summary="复制他场装修到本场（保护历史证据）")
def copy_room(session_id: int, payload: RoomCopyIn, user: CurrentUser, db: DbDep) -> dict:
    target = get_owned_session(db, user, session_id)
    source = get_session_or_404(db, payload.from_session_id)
    assert_session_access(db, user, source)
    if not source.room_config:
        raise errors.validation_error("来源场次没有可复制的装修配置", {"from_session_id": source.id})
    target.room_config = dict(source.room_config)
    db.commit()
    return target.room_config


@router.get("/sessions/{session_id}/preflight", response_model=PreflightOut, summary="开播检查")
def preflight(session_id: int, user: CurrentUser, db: DbDep) -> PreflightOut:
    from app.services import preflight as preflight_service

    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    return PreflightOut.model_validate(preflight_service.build_checklist(db, session))
