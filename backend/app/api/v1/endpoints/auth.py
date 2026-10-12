"""认证接口：登录 / 当前用户 / 修改口令。"""

from fastapi import APIRouter
from sqlalchemy import select

from app.core import errors
from app.core.deps import CurrentUser, DbDep
from app.core.enums import UserStatus
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.identity import ChangePasswordIn, LoginIn, TokenOut, UserOut

router = APIRouter(tags=["认证"])


@router.post("/auth/login", response_model=TokenOut, summary="登录")
def login(payload: LoginIn, db: DbDep) -> TokenOut:
    user = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise errors.AppError(errors.INVALID_CREDENTIALS, "用户名或口令错误", 401)
    if user.status != UserStatus.ACTIVE:
        raise errors.AppError(errors.ACCOUNT_DISABLED, "账号已停用，请联系管理员", 403)
    token, expires_in = create_access_token(user.id, user.role)
    return TokenOut(token=token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut, summary="当前登录用户")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/auth/change-password", response_model=UserOut, summary="修改本人登录口令")
def change_password(payload: ChangePasswordIn, user: CurrentUser, db: DbDep) -> UserOut:
    if not verify_password(payload.old_password, user.password_hash):
        raise errors.AppError(errors.INVALID_CREDENTIALS, "原口令不正确", 400)
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return UserOut.model_validate(user)
