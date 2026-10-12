"""AI 岗位智能体相关模式。"""

from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import AgentPosition
from app.schemas.common import ORMModel, UtcDatetime


class AgentCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    position_type: AgentPosition
    duty: str = ""
    instructions: str = ""
    skills: list[str] = []
    tools: list[str] = []
    triggers: list[str] = []
    knowledge_cards: list[str] = []
    avatar: str = ""
    from_template_id: int | None = None  # 从内置模板创建


class AgentPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    position_type: AgentPosition | None = None
    duty: str | None = None
    instructions: str | None = None
    skills: list[str] | None = None
    tools: list[str] | None = None
    triggers: list[str] | None = None
    knowledge_cards: list[str] | None = None
    avatar: str | None = None


class AgentOut(ORMModel):
    id: int
    name: str
    position_type: str
    duty: str
    instructions: str
    skills: list = []
    tools: list = []
    triggers: list = []
    knowledge_cards: list = []
    avatar: str
    completeness: float
    scope: str
    class_id: int | None = None
    owner_id: int | None = None
    status: str
    review_note: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class AgentInputIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    context: dict = {}


class AgentRunOut(ORMModel):
    id: int
    agent_id: int
    session_id: int | None = None
    task_id: int | None = None
    user_id: int
    input: dict = {}
    output: dict = {}
    source: str
    trace: list = []
    latency_ms: int
    model: str
    rating_score: int | None = None
    rating_comment: str
    adopted_target: str | None = None
    adopted_at: UtcDatetime | None = None
    created_at: UtcDatetime


class RehearseOut(BaseModel):
    """预演结果：不写入正式业务，也不落 run 记录。"""

    output: dict
    source: str
    trace: list = []
    latency_ms: int = 0
    model: str = ""
    persist: bool = False


class AdoptIn(BaseModel):
    target: Literal["script", "report"]
    note: str = ""


class AdoptOut(BaseModel):
    run_id: int
    target: str
    applied_to: dict
    adopted_at: UtcDatetime


class ReviewIn(BaseModel):
    action: Literal["approve", "reject"]
    note: str = ""


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str = ""
