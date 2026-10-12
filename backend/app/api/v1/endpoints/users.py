"""用户管理：管理员建号/停用；教师可批量导入本班学生。

注意：停用后既有登录态立即失效（deps.get_current_user 每次请求校验状态）。
"""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core import errors
from app.core.deps import AdminDep, CurrentUser, DbDep, TeacherDep
from app.core.enums import Role, UserStatus
from app.core.security import hash_password
from app.models.user import Klass, User
from app.schemas.common import Page
from app.schemas.identity import (
    ImportSkipped,
    ImportStudentsIn,
    ImportStudentsOut,
    UserCreateIn,
    UserOut,
    UserPatchIn,
)

router = APIRouter(tags=["用户管理"])


@router.post("/users", response_model=UserOut, summary="创建账号（管理员）")
def create_user(payload: UserCreateIn, admin: AdminDep, db: DbDep) -> UserOut:
    exists = db.execute(select(User.id).where(User.username == payload.username)).first()
    if exists:
        raise errors.AppError(errors.DUPLICATE, f"账号已存在：{payload.username}", 409)
    if payload.class_id is not None and db.get(Klass, payload.class_id) is None:
        raise errors.not_found("班级", payload.class_id)
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=str(payload.role),
        real_name=payload.real_name,
        class_id=payload.class_id,
    )
    db.add(user)
    db.commit()
    return UserOut.model_validate(user)


@router.get("/users", response_model=Page[UserOut], summary="账号列表")
def list_users(
    user: TeacherDep,
    db: DbDep,
    role: Role | None = None,
    class_id: int | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[UserOut]:
    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if user.role == Role.TEACHER:
        # 教师仅可见所带班级学生与本人
        klass_ids = select(Klass.id).where(Klass.teacher_id == user.id).scalar_subquery()
        cond = (User.class_id.in_(klass_ids)) | (User.id == user.id)
        stmt, count_stmt = stmt.where(cond), count_stmt.where(cond)
    if role is not None:
        stmt, count_stmt = stmt.where(User.role == role), count_stmt.where(User.role == role)
    if class_id is not None:
        stmt, count_stmt = stmt.where(User.class_id == class_id), count_stmt.where(User.class_id == class_id)
    if keyword:
        like = f"%{keyword}%"
        cond = User.username.like(like) | User.real_name.like(like)
        stmt, count_stmt = stmt.where(cond), count_stmt.where(cond)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows], total=total, page=page, page_size=page_size
    )


@router.get("/users/{user_id}", response_model=UserOut, summary="账号详情")
def get_user(user_id: int, user: CurrentUser, db: DbDep) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise errors.not_found("用户", user_id)
    if user.role == Role.STUDENT and user.id != target.id:
        raise errors.permission_denied("学生只能查看本人信息")
    if user.role == Role.TEACHER and target.id != user.id:
        klass = db.get(Klass, target.class_id) if target.class_id else None
        if klass is None or klass.teacher_id != user.id:
            raise errors.permission_denied("教师只能查看所带班级学生")
    return UserOut.model_validate(target)


@router.patch("/users/{user_id}", response_model=UserOut, summary="修改账号（管理员）")
def patch_user(user_id: int, payload: UserPatchIn, admin: AdminDep, db: DbDep) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise errors.not_found("用户", user_id)
    if payload.real_name is not None:
        target.real_name = payload.real_name
    if payload.class_id is not None:
        if db.get(Klass, payload.class_id) is None:
            raise errors.not_found("班级", payload.class_id)
        target.class_id = payload.class_id
    if payload.status is not None:
        target.status = str(payload.status)
    if payload.role is not None:
        target.role = str(payload.role)
    db.commit()
    return UserOut.model_validate(target)


@router.post("/users/import", response_model=ImportStudentsOut, summary="批量导入学生（管理员/教师）")
def import_students(payload: ImportStudentsIn, user: TeacherDep, db: DbDep) -> ImportStudentsOut:
    from app.core.deps import assert_class_access, get_class_or_404

    klass = get_class_or_404(db, payload.class_id)
    assert_class_access(user, klass)
    created: list[UserOut] = []
    skipped: list[ImportSkipped] = []
    seen: set[str] = set()
    for row in payload.students:
        if row.username in seen:
            skipped.append(ImportSkipped(username=row.username, reason="批次内重复账号"))
            continue
        seen.add(row.username)
        exists = db.execute(select(User.id).where(User.username == row.username)).first()
        if exists:
            skipped.append(ImportSkipped(username=row.username, reason="账号已存在"))
            continue
        student = User(
            username=row.username,
            password_hash=hash_password(row.password),
            role=str(Role.STUDENT),
            real_name=row.real_name,
            class_id=klass.id,
            status=str(UserStatus.ACTIVE),
        )
        db.add(student)
        db.flush()
        created.append(UserOut.model_validate(student))
    db.commit()
    return ImportStudentsOut(created=created, skipped=skipped)
