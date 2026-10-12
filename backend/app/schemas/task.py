"""任务与场次（经营准备）相关模式。"""

from pydantic import BaseModel, Field

from app.core.enums import ItemRole, ScriptStage, TaskMode, TaskStatus
from app.schemas.common import ORMModel, UtcDatetime


class TaskCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="")
    class_id: int
    mode: TaskMode = TaskMode.PERSONAL
    initial_fund_cents: int = Field(default=5_000_000, ge=0)  # 初始经营资金（分）
    market_heat: float = Field(default=5.0, ge=1, le=10)
    competition_level: float = Field(default=5.0, ge=1, le=10)
    strict_mode: bool = False
    start_at: UtcDatetime | None = None
    end_at: UtcDatetime | None = None
    weight_config: dict = {}


class TaskPatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    initial_fund_cents: int | None = Field(default=None, ge=0)
    market_heat: float | None = Field(default=None, ge=1, le=10)
    competition_level: float | None = Field(default=None, ge=1, le=10)
    strict_mode: bool | None = None
    start_at: UtcDatetime | None = None
    end_at: UtcDatetime | None = None
    weight_config: dict | None = None
    status: TaskStatus | None = None


class TaskOut(ORMModel):
    id: int
    title: str
    description: str
    class_id: int
    created_by: int
    mode: str
    status: str
    initial_fund_cents: int
    market_heat: float
    competition_level: float
    strict_mode: bool
    start_at: UtcDatetime | None = None
    end_at: UtcDatetime | None = None
    weight_config: dict = {}
    agent_assignments: list = []
    created_at: UtcDatetime
    updated_at: UtcDatetime


class SessionCreateIn(BaseModel):
    team_id: int | None = None
    name: str = Field(default="", max_length=200)


class SessionOut(ORMModel):
    id: int
    task_id: int
    owner_id: int
    team_id: int | None = None
    name: str
    status: str
    fund_balance_cents: int
    research: dict | None = None
    plan: dict | None = None
    script: dict | None = None
    room_config: dict | None = None
    metrics: dict = {}
    started_at: UtcDatetime | None = None
    ended_at: UtcDatetime | None = None
    submitted_at: UtcDatetime | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime


# ---- 经营准备各环节的提交物 ----

class ResearchIn(BaseModel):
    """调研纪要。target_audience 与 reasons 为必填——缺信息时要显式报错，不默认放行。"""

    target_audience: str = Field(min_length=1, description="目标人群")
    reasons: str = Field(min_length=1, description="选品理由/结论")
    competitors: str = ""
    price_band: str = ""
    selling_points: list[str] = []
    recommended_slot: str = ""


class ScheduleSlot(BaseModel):
    time: str = ""
    content: str = ""


class PlanGoals(BaseModel):
    gmv_cents: int = Field(default=0, ge=0)
    orders: int = Field(default=0, ge=0)


class PlanIn(BaseModel):
    theme: str = Field(min_length=1, max_length=200)
    target_audience: str = ""
    goals: PlanGoals = PlanGoals()
    schedule: list[ScheduleSlot] = []
    main_items: list[int] = []  # session_items.id


class ScriptSegmentIn(BaseModel):
    stage: ScriptStage
    item_id: int | None = None
    duration_min: float = Field(default=0, ge=0)
    speech: str = ""
    actions: list[str] = []


class ScriptIn(BaseModel):
    segments: list[ScriptSegmentIn] = []


class RoomCanvasIn(BaseModel):
    ratio: str = Field(default="9:16", pattern="^(9:16|16:9)$")
    elements: list[dict] = []


class RoomIn(BaseModel):
    background: str = ""
    canvas: RoomCanvasIn = RoomCanvasIn()
    title: str = ""
    subtitle: str = ""
    notice: str = ""
    welcome: str = ""
    sensitive_words: list[str] = []
    quick_phrases: list[str] = []
    faq: list[dict] = []
    cover_url: str = ""
    intro: str = ""
    planned_start_at: UtcDatetime | None = None


class RoomCopyIn(BaseModel):
    from_session_id: int


class PreflightItemOut(BaseModel):
    key: str
    label: str
    required: bool
    passed: bool
    reason: str = ""
    entry: str = ""  # 前端跳转锚点，如 "cart" / "script"


class PreflightOut(BaseModel):
    session_id: int
    strict_mode: bool
    passed: bool
    items: list[PreflightItemOut]


class CartItemRoleIn(BaseModel):
    role: ItemRole
