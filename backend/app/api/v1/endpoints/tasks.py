"""任务：创建/发布/关闭、开播前阶段清单、智能体作业布置。"""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core import errors
from app.core.deps import (
    CurrentUser,
    DbDep,
    TeacherDep,
    assert_class_access,
    assert_session_access,
    assert_task_access,
    get_class_or_404,
    get_task_or_404,
)
from app.core.enums import Role, TaskStatus
from app.models.agent import Agent, AgentRun
from app.models.task import Task
from app.models.user import User
from app.schemas.common import Page
from app.schemas.evaluation import AgentAssignmentIn
from app.schemas.task import PreflightOut, TaskCreateIn, TaskOut, TaskPatchIn

router = APIRouter(tags=["任务"])


@router.post("/tasks", response_model=TaskOut, summary="创建任务（教师/管理员）")
def create_task(payload: TaskCreateIn, user: TeacherDep, db: DbDep) -> TaskOut:
    klass = get_class_or_404(db, payload.class_id)
    assert_class_access(user, klass)
    task = Task(
        title=payload.title,
        description=payload.description,
        class_id=payload.class_id,
        created_by=user.id,
        mode=str(payload.mode),
        status=str(TaskStatus.DRAFT),
        initial_fund_cents=payload.initial_fund_cents,
        market_heat=payload.market_heat,
        competition_level=payload.competition_level,
        strict_mode=payload.strict_mode,
        start_at=payload.start_at,
        end_at=payload.end_at,
        weight_config=payload.weight_config,
    )
    db.add(task)
    db.commit()
    return TaskOut.model_validate(task)


@router.get("/tasks", response_model=Page[TaskOut], summary="任务列表（按角色范围）")
def list_tasks(
    user: CurrentUser,
    db: DbDep,
    status: TaskStatus | None = None,
    class_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[TaskOut]:
    stmt, count_stmt = select(Task), select(func.count(Task.id))
    if user.role == Role.TEACHER:
        cond = Task.created_by == user.id
    elif user.role == Role.STUDENT:
        cond = (Task.class_id == user.class_id) & (Task.status != TaskStatus.DRAFT)
    else:
        cond = None
    if cond is not None:
        stmt, count_stmt = stmt.where(cond), count_stmt.where(cond)
    if status is not None:
        stmt, count_stmt = stmt.where(Task.status == status), count_stmt.where(Task.status == status)
    if class_id is not None:
        stmt, count_stmt = stmt.where(Task.class_id == class_id), count_stmt.where(Task.class_id == class_id)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(Task.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[TaskOut](
        items=[TaskOut.model_validate(t) for t in rows], total=total, page=page, page_size=page_size
    )


@router.get("/tasks/{task_id}", response_model=TaskOut, summary="任务详情")
def get_task(task_id: int, user: CurrentUser, db: DbDep) -> TaskOut:
    task = get_task_or_404(db, task_id)
    assert_task_access(user, task)
    return TaskOut.model_validate(task)


@router.patch("/tasks/{task_id}", response_model=TaskOut, summary="修改任务（草稿阶段）")
def patch_task(task_id: int, payload: TaskPatchIn, user: TeacherDep, db: DbDep) -> TaskOut:
    task = get_task_or_404(db, task_id)
    if user.role != Role.ADMIN and task.created_by != user.id:
        raise errors.permission_denied("仅任务创建教师可修改任务")
    if task.status == TaskStatus.CLOSED:
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, "已关闭的任务不可修改", 400)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(task, key, str(value) if key == "status" and value is not None else value)
    db.commit()
    return TaskOut.model_validate(task)


@router.post("/tasks/{task_id}/publish", response_model=TaskOut, summary="发布任务")
def publish_task(task_id: int, user: TeacherDep, db: DbDep) -> TaskOut:
    task = get_task_or_404(db, task_id)
    if user.role != Role.ADMIN and task.created_by != user.id:
        raise errors.permission_denied("仅任务创建教师可发布任务")
    if task.status != TaskStatus.DRAFT:
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, f"当前状态 {task.status} 不能发布", 400)
    task.status = str(TaskStatus.PUBLISHED)
    db.commit()
    return TaskOut.model_validate(task)


@router.post("/tasks/{task_id}/close", response_model=TaskOut, summary="关闭任务")
def close_task(task_id: int, user: TeacherDep, db: DbDep) -> TaskOut:
    task = get_task_or_404(db, task_id)
    if user.role != Role.ADMIN and task.created_by != user.id:
        raise errors.permission_denied("仅任务创建教师可关闭任务")
    if task.status != TaskStatus.PUBLISHED:
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, f"当前状态 {task.status} 不能关闭", 400)
    task.status = str(TaskStatus.CLOSED)
    db.commit()
    return TaskOut.model_validate(task)


@router.get("/tasks/{task_id}/checklist", response_model=PreflightOut, summary="开播前阶段清单")
def task_checklist(
    task_id: int, user: CurrentUser, db: DbDep, session_id: int = Query(...)
) -> PreflightOut:
    from app.models.task import TrainingSession
    from app.services import preflight

    task = get_task_or_404(db, task_id)
    assert_task_access(user, task)
    session = db.get(TrainingSession, session_id)
    if session is None or session.task_id != task.id:
        raise errors.validation_error("session_id 与该任务不匹配", {"session_id": session_id})
    assert_session_access(db, user, session)
    return PreflightOut.model_validate(preflight.build_checklist(db, session))


@router.post("/tasks/{task_id}/agent-assignments", response_model=TaskOut, summary="布置智能体作业（教师）")
def assign_agent(task_id: int, payload: AgentAssignmentIn, user: TeacherDep, db: DbDep) -> TaskOut:
    task = get_task_or_404(db, task_id)
    if user.role != Role.ADMIN and task.created_by != user.id:
        raise errors.permission_denied("仅任务创建教师可布置作业")
    agent = db.get(Agent, payload.agent_id)
    if agent is None:
        raise errors.not_found("智能体", payload.agent_id)
    if agent.scope == "personal" and agent.owner_id != user.id:
        raise errors.permission_denied("不能布置他人的个人智能体")
    assignments = list(task.agent_assignments or [])
    assignments.append({"agent_id": agent.id, "agent_name": agent.name, "instructions": payload.instructions})
    task.agent_assignments = assignments
    db.commit()
    return TaskOut.model_validate(task)


@router.get("/tasks/{task_id}/agent-runs", summary="任务下智能体运行记录（教师）")
def task_agent_runs(
    task_id: int,
    user: TeacherDep,
    db: DbDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    from app.schemas.agent import AgentRunOut

    task = get_task_or_404(db, task_id)
    if user.role != Role.ADMIN and task.created_by != user.id:
        raise errors.permission_denied("仅任务创建教师可查看作业运行记录")
    count = db.execute(
        select(func.count(AgentRun.id)).where(AgentRun.task_id == task_id)
    ).scalar_one()
    rows = db.execute(
        select(AgentRun, User)
        .join(User, User.id == AgentRun.user_id)
        .where(AgentRun.task_id == task_id)
        .order_by(AgentRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for run, u in rows:
        data = AgentRunOut.model_validate(run).model_dump()
        data["student_name"] = u.real_name or u.username
        items.append(data)
    return {"items": items, "total": int(count), "page": page, "page_size": page_size}
