"""认证、用户、班级、团队相关模式。"""

from pydantic import BaseModel, Field

from app.core.enums import Role, TeamPosition, UserStatus
from app.schemas.common import ORMModel, UtcDatetime


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORMModel):
    id: int
    username: str
    role: str
    real_name: str
    class_id: int | None = None
    status: str
    created_at: UtcDatetime


class TokenOut(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserOut


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6, max_length=128)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: Role
    real_name: str = Field(default="", max_length=64)
    class_id: int | None = None


class UserPatchIn(BaseModel):
    real_name: str | None = Field(default=None, max_length=64)
    class_id: int | None = None
    status: UserStatus | None = None
    role: Role | None = None


class ImportStudentIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    real_name: str = Field(default="", max_length=64)
    password: str = Field(default="Student@123", min_length=6)


class ImportStudentsIn(BaseModel):
    class_id: int
    students: list[ImportStudentIn] = Field(min_length=1, max_length=200)


class ImportSkipped(BaseModel):
    username: str
    reason: str


class ImportStudentsOut(BaseModel):
    created: list[UserOut]
    skipped: list[ImportSkipped]


class ClassCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=255)


class ClassPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=255)
    status: str | None = None


class ClassOut(ORMModel):
    id: int
    name: str
    description: str
    teacher_id: int
    status: str
    created_at: UtcDatetime
    student_count: int = 0
    team_count: int = 0


class AddStudentsIn(BaseModel):
    user_ids: list[int] = Field(min_length=1)


class TeamCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class TeamPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    status: str | None = None


class TeamMemberIn(BaseModel):
    user_id: int
    position: TeamPosition


class TeamMemberOut(ORMModel):
    id: int
    user_id: int
    username: str = ""
    real_name: str = ""
    position: str
    joined_at: UtcDatetime


class TeamOut(ORMModel):
    id: int
    class_id: int
    name: str
    invite_code: str | None = None
    status: str
    created_at: UtcDatetime
    members: list[TeamMemberOut] = []


class AddStudentsOut(BaseModel):
    added: list[UserOut]
    skipped: list[ImportSkipped]
