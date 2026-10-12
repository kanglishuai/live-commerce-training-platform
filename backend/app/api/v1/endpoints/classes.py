"""班级、团队（小组）、成员岗位管理。"""

import secrets

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core import errors
from app.core.deps import (
    AdminDep,
    CurrentUser,
    DbDep,
    TeacherDep,
    assert_class_access,
    get_class_or_404,
)
from app.core.enums import Role, UserStatus
from app.models.user import Klass, Team, TeamMember, User
from app.schemas.common import OkOut, Page
from app.schemas.identity import (
    AddStudentsIn,
    AddStudentsOut,
    ClassCreateIn,
    ClassOut,
    ClassPatchIn,
    ImportSkipped,
    TeamCreateIn,
    TeamMemberIn,
    TeamMemberOut,
    TeamOut,
    TeamPatchIn,
    UserOut,
)

router = APIRouter(tags=["班级与团队"])


def _class_out(db: DbDep, klass: Klass) -> ClassOut:
    student_count = db.execute(
        select(func.count(User.id)).where(User.class_id == klass.id, User.role == Role.STUDENT)
    ).scalar_one()
    team_count = db.execute(
        select(func.count(Team.id)).where(Team.class_id == klass.id)
    ).scalar_one()
    out = ClassOut.model_validate(klass)
    out.student_count = int(student_count)
    out.team_count = int(team_count)
    return out


def _team_out(db: DbDep, team: Team) -> TeamOut:
    members = db.execute(
        select(TeamMember, User).join(User, User.id == TeamMember.user_id).where(
            TeamMember.team_id == team.id
        )
    ).all()
    out = TeamOut.model_validate(team)
    out.members = [
        TeamMemberOut(
            id=m.id,
            user_id=m.user_id,
            username=u.username,
            real_name=u.real_name,
            position=m.position,
            joined_at=m.joined_at,
        )
        for m, u in members
    ]
    return out


# ---- 班级 ----

@router.post("/classes", response_model=ClassOut, summary="创建班级（教师/管理员）")
def create_class(payload: ClassCreateIn, user: TeacherDep, db: DbDep) -> ClassOut:
    klass = Klass(name=payload.name, description=payload.description, teacher_id=user.id)
    db.add(klass)
    db.commit()
    return _class_out(db, klass)


@router.get("/classes", response_model=list[ClassOut], summary="班级列表（按角色范围）")
def list_classes(user: CurrentUser, db: DbDep) -> list[ClassOut]:
    if user.role == Role.ADMIN:
        rows = db.execute(select(Klass).order_by(Klass.id)).scalars().all()
    elif user.role == Role.TEACHER:
        rows = db.execute(
            select(Klass).where(Klass.teacher_id == user.id).order_by(Klass.id)
        ).scalars().all()
    else:
        rows = (
            db.execute(select(Klass).where(Klass.id == user.class_id)).scalars().all()
            if user.class_id
            else []
        )
    return [_class_out(db, k) for k in rows]


@router.get("/classes/{class_id}", response_model=ClassOut, summary="班级详情")
def get_class(class_id: int, user: CurrentUser, db: DbDep) -> ClassOut:
    klass = get_class_or_404(db, class_id)
    assert_class_access(user, klass)
    return _class_out(db, klass)


@router.patch("/classes/{class_id}", response_model=ClassOut, summary="修改班级（管理员/班主任教师）")
def patch_class(class_id: int, payload: ClassPatchIn, user: TeacherDep, db: DbDep) -> ClassOut:
    klass = get_class_or_404(db, class_id)
    if user.role != Role.ADMIN and klass.teacher_id != user.id:
        raise errors.permission_denied("仅班主任教师可修改班级")
    if payload.name is not None:
        klass.name = payload.name
    if payload.description is not None:
        klass.description = payload.description
    if payload.status is not None:
        klass.status = payload.status
    db.commit()
    return _class_out(db, klass)


@router.post("/classes/{class_id}/students", response_model=AddStudentsOut, summary="将学生加入班级")
def add_students(
    class_id: int, payload: AddStudentsIn, user: TeacherDep, db: DbDep
) -> AddStudentsOut:
    klass = get_class_or_404(db, class_id)
    assert_class_access(user, klass)
    added: list[UserOut] = []
    skipped: list[ImportSkipped] = []
    for uid in payload.user_ids:
        target = db.get(User, uid)
        if target is None:
            skipped.append(ImportSkipped(username=str(uid), reason="用户不存在"))
            continue
        if target.role != Role.STUDENT:
            skipped.append(ImportSkipped(username=target.username, reason="仅学生账号可加入班级"))
            continue
        if target.class_id == class_id:
            skipped.append(ImportSkipped(username=target.username, reason="已在班级中"))
            continue
        target.class_id = class_id
        added.append(UserOut.model_validate(target))
    db.commit()
    return AddStudentsOut(added=added, skipped=skipped)


@router.get("/classes/{class_id}/students", response_model=Page[UserOut], summary="班级学生列表")
def list_students(
    class_id: int,
    user: CurrentUser,
    db: DbDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[UserOut]:
    klass = get_class_or_404(db, class_id)
    assert_class_access(user, klass)
    base = select(User).where(User.class_id == class_id, User.role == Role.STUDENT)
    total = db.execute(select(func.count(User.id)).where(User.class_id == class_id, User.role == Role.STUDENT)).scalar_one()
    rows = db.execute(
        base.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows], total=total, page=page, page_size=page_size
    )


# ---- 团队（小组）----

@router.post("/classes/{class_id}/teams", response_model=TeamOut, summary="创建团队（教师/学生）")
def create_team(class_id: int, payload: TeamCreateIn, user: CurrentUser, db: DbDep) -> TeamOut:
    klass = get_class_or_404(db, class_id)
    assert_class_access(user, klass)
    team = Team(
        class_id=class_id,
        name=payload.name,
        invite_code=secrets.token_hex(4).upper(),
        created_by=user.id,
    )
    db.add(team)
    db.flush()
    if user.role == Role.STUDENT:
        db.add(TeamMember(team_id=team.id, user_id=user.id, position="host"))
    db.commit()
    return _team_out(db, team)


@router.get("/classes/{class_id}/teams", response_model=list[TeamOut], summary="班级团队列表")
def list_teams(class_id: int, user: CurrentUser, db: DbDep) -> list[TeamOut]:
    klass = get_class_or_404(db, class_id)
    assert_class_access(user, klass)
    rows = db.execute(
        select(Team).where(Team.class_id == class_id).order_by(Team.id)
    ).scalars().all()
    return [_team_out(db, t) for t in rows]


@router.get("/teams/{team_id}", response_model=TeamOut, summary="团队详情")
def get_team(team_id: int, user: CurrentUser, db: DbDep) -> TeamOut:
    team = db.get(Team, team_id)
    if team is None:
        raise errors.not_found("团队", team_id)
    assert_class_access(user, get_class_or_404(db, team.class_id))
    return _team_out(db, team)


@router.patch("/teams/{team_id}", response_model=TeamOut, summary="修改团队（教师/创建者）")
def patch_team(team_id: int, payload: TeamPatchIn, user: CurrentUser, db: DbDep) -> TeamOut:
    team = db.get(Team, team_id)
    if team is None:
        raise errors.not_found("团队", team_id)
    klass = get_class_or_404(db, team.class_id)
    if not (user.role == Role.ADMIN or klass.teacher_id == user.id or team.created_by == user.id):
        raise errors.permission_denied("仅教师或团队创建者可修改团队")
    if payload.name is not None:
        team.name = payload.name
    if payload.status is not None:
        team.status = payload.status
    db.commit()
    return _team_out(db, team)


@router.delete("/teams/{team_id}", response_model=OkOut, summary="解散团队（教师/创建者）")
def delete_team(team_id: int, user: CurrentUser, db: DbDep) -> OkOut:
    team = db.get(Team, team_id)
    if team is None:
        raise errors.not_found("团队", team_id)
    klass = get_class_or_404(db, team.class_id)
    if not (user.role == Role.ADMIN or klass.teacher_id == user.id or team.created_by == user.id):
        raise errors.permission_denied("仅教师或团队创建者可解散团队")
    from app.models.task import TrainingSession

    used = db.execute(
        select(TrainingSession.id).where(TrainingSession.team_id == team_id).limit(1)
    ).first()
    if used:
        raise errors.AppError(errors.STATE_TRANSITION_INVALID, "团队已关联场次，不能直接解散", 400)
    db.execute(TeamMember.__table__.delete().where(TeamMember.team_id == team_id))
    db.delete(team)
    db.commit()
    return OkOut(detail=f"团队 {team_id} 已解散")


@router.post("/teams/{team_id}/members", response_model=TeamOut, summary="添加团队成员并配置岗位")
def add_member(team_id: int, payload: TeamMemberIn, user: CurrentUser, db: DbDep) -> TeamOut:
    team = db.get(Team, team_id)
    if team is None:
        raise errors.not_found("团队", team_id)
    klass = get_class_or_404(db, team.class_id)
    assert_class_access(user, klass)
    target = db.get(User, payload.user_id)
    if target is None or target.class_id != klass.id:
        raise errors.validation_error("目标成员必须是本班学生", {"user_id": payload.user_id})
    exists = db.execute(
        select(TeamMember.id).where(
            TeamMember.team_id == team_id, TeamMember.user_id == payload.user_id
        )
    ).first()
    if exists:
        raise errors.AppError(errors.DUPLICATE, "该成员已在团队中（岗位可通过移除后重新添加调整）", 409)
    db.add(TeamMember(team_id=team_id, user_id=payload.user_id, position=str(payload.position)))
    db.commit()
    return _team_out(db, team)


@router.delete("/teams/{team_id}/members/{user_id}", response_model=TeamOut, summary="移除团队成员")
def remove_member(team_id: int, user_id: int, user: CurrentUser, db: DbDep) -> TeamOut:
    team = db.get(Team, team_id)
    if team is None:
        raise errors.not_found("团队", team_id)
    klass = get_class_or_404(db, team.class_id)
    if not (user.role == Role.ADMIN or klass.teacher_id == user.id or team.created_by == user.id):
        raise errors.permission_denied("仅教师或团队创建者可移除成员")
    member = db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    ).scalar_one_or_none()
    if member is None:
        raise errors.not_found("团队成员", user_id)
    db.delete(member)
    db.commit()
    return _team_out(db, team)
