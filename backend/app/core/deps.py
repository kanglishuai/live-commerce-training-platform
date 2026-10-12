"""FastAPI 依赖：数据库会话、当前用户、角色校验、资源级访问控制。

权限原则（对应题目第 4 章）：
- 学生之间不能互相读取场次；学生只能操作自己的场次/团队。
- 教师只管理自己创建的班级/任务/所带学生的场次。
- 管理员全局可见。
- 停用账号（status=disabled）后，既有令牌立即失效（每次请求校验状态）。
"""

from collections.abc import Callable, Iterator
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core import errors
from app.core.enums import Role, UserStatus
from app.core.security import decode_access_token
from app.db.base import get_session_factory
from app.models.task import Task, TrainingSession
from app.models.user import Klass, User


def get_db() -> Iterator[OrmSession]:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbDep = Annotated[OrmSession, Depends(get_db)]


def get_current_user(request: Request, db: DbDep) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise errors.AppError(errors.AUTH_REQUIRED, "缺少 Bearer 令牌", 401)
    token = auth.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except pyjwt.PyJWTError as exc:
        raise errors.AppError(errors.AUTH_REQUIRED, f"令牌无效或已过期：{exc}", 401) from exc
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise errors.AppError(errors.AUTH_REQUIRED, "用户不存在", 401)
    if user.status != UserStatus.ACTIVE:
        raise errors.AppError(errors.ACCOUNT_DISABLED, "账号已停用", 403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], User]:
    allowed = {str(r) for r in roles}

    def checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise errors.permission_denied(f"该操作仅限 {'/'.join(allowed)} 角色")
        return user

    return checker


# ---- 资源级访问控制 ----

def get_class_or_404(db: OrmSession, class_id: int) -> Klass:
    klass = db.get(Klass, class_id)
    if klass is None:
        raise errors.not_found("班级", class_id)
    return klass


def assert_class_access(user: User, klass: Klass) -> None:
    """管理员任意；教师限自己所带班级；学生限自己所在班级。"""
    if user.role == Role.ADMIN:
        return
    if user.role == Role.TEACHER and klass.teacher_id == user.id:
        return
    if user.role == Role.STUDENT and user.class_id == klass.id:
        return
    raise errors.permission_denied("无权访问该班级")


def get_task_or_404(db: OrmSession, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise errors.not_found("任务", task_id)
    return task


def assert_task_access(user: User, task: Task) -> None:
    if user.role == Role.ADMIN:
        return
    if user.role == Role.TEACHER and task.created_by == user.id:
        return
    if user.role == Role.STUDENT and task.class_id == user.class_id and task.status != "draft":
        return
    raise errors.permission_denied("无权访问该任务")


def get_session_or_404(db: OrmSession, session_id: int) -> TrainingSession:
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise errors.not_found("场次", session_id)
    return session


def assert_session_access(db: OrmSession, user: User, session: TrainingSession) -> None:
    """学生仅本人场次（团队场次允许同队成员）；教师限所带班级的场次；管理员任意。"""
    if user.role == Role.ADMIN:
        return
    if session.owner_id == user.id:
        return
    if user.role == Role.TEACHER:
        task = db.get(Task, session.task_id)
        if task is not None:
            klass = db.get(Klass, task.class_id)
            if klass is not None and klass.teacher_id == user.id:
                return
    if user.role == Role.STUDENT and session.team_id is not None:
        from app.models.user import TeamMember

        member = db.execute(
            select(TeamMember).where(
                TeamMember.team_id == session.team_id, TeamMember.user_id == user.id
            )
        ).scalar_one_or_none()
        if member is not None:
            return
    raise errors.permission_denied("无权访问该场次")


def get_owned_session(db: OrmSession, user: User, session_id: int) -> TrainingSession:
    """仅允许场次归属人（含同队成员）操作，用于写入类接口。"""
    session = get_session_or_404(db, session_id)
    if user.role == Role.ADMIN:
        return session
    if session.owner_id == user.id:
        return session
    if user.role == Role.STUDENT and session.team_id is not None:
        from app.models.user import TeamMember

        member = db.execute(
            select(TeamMember).where(
                TeamMember.team_id == session.team_id, TeamMember.user_id == user.id
            )
        ).scalar_one_or_none()
        if member is not None:
            return session
    raise errors.permission_denied("该场次仅归属人可修改")


AdminDep = Annotated[User, Depends(require_roles(Role.ADMIN))]
TeacherDep = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TEACHER))]
