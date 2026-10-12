"""复盘报告、成绩、竞赛相关模式。"""

from pydantic import BaseModel, Field

from app.core.enums import CompetitionMetric
from app.schemas.common import ORMModel, UtcDatetime


class ReportOut(ORMModel):
    id: int
    session_id: int
    content: dict = {}
    source: str  # llm / rule —— 规则兜底必须明确标识
    generated_at: UtcDatetime | None = None
    improvement_plan: str
    status: str
    locked: bool
    submitted_at: UtcDatetime | None = None
    returned_reason: str


class ReportUpdateIn(BaseModel):
    improvement_plan: str = Field(min_length=1)


class ReportReturnIn(BaseModel):
    reason: str = Field(min_length=1)


class ScoreIn(BaseModel):
    subjective_score: float = Field(ge=0, le=100)
    comment: str = ""


class ScoreOut(ORMModel):
    id: int
    session_id: int
    objective_score: float
    objective_detail: dict = {}
    subjective_score: float | None = None
    comprehensive_score: float | None = None
    comment: str
    weights: dict = {}
    teacher_id: int | None = None
    scored_at: UtcDatetime | None = None


class MetricsOut(BaseModel):
    session_id: int
    view: str
    data: dict
    notes: list[str] = []  # 数据来源与估算口径说明（题目要求明示）


class ClassReportOut(BaseModel):
    class_id: int
    class_name: str
    summary: dict
    students: list[dict]


class PatrolOut(BaseModel):
    class_id: int
    groups: list[dict]


class CompetitionCreateIn(BaseModel):
    class_id: int
    name: str = Field(min_length=1, max_length=200)
    metric: CompetitionMetric = CompetitionMetric.COMPREHENSIVE
    task_id: int | None = None
    rules: dict = {}


class CompetitionOut(ORMModel):
    id: int
    class_id: int
    task_id: int | None = None
    name: str
    metric: str
    rules: dict = {}
    status: str
    created_by: int
    created_at: UtcDatetime


class LeaderboardOut(BaseModel):
    competition_id: int
    metric: str
    entries: list[dict]


class AgentAssignmentIn(BaseModel):
    agent_id: int
    instructions: str = ""


class OkMessageOut(BaseModel):
    ok: bool = True
    message: str = ""
