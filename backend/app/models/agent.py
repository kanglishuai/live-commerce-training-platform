"""AI 岗位智能体：配置、预演/正式运行记录、采纳轨迹。

约束（对应题目第 13 章）：
- 「先生成、后采纳」：AgentRun 只记录生成结果，只有显式 adopt 才写入脚本/复盘。
- 正式运行保留输入、输出、数据来源、工具轨迹、耗时与模型来源；规则兜底与 LLM 输出以 source 区分。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    position_type: Mapped[str] = mapped_column(String(32), index=True)  # AgentPosition
    duty: Mapped[str] = mapped_column(Text, default="")  # 职责
    instructions: Mapped[str] = mapped_column(Text, default="")  # 行为指令
    skills: Mapped[list] = mapped_column(JSON, default=list)  # 技能映射
    tools: Mapped[list] = mapped_column(JSON, default=list)  # 数据工具
    triggers: Mapped[list] = mapped_column(JSON, default=list)  # 触发条件
    knowledge_cards: Mapped[list] = mapped_column(JSON, default=list)  # 知识卡
    avatar: Mapped[str] = mapped_column(String(255), default="")

    completeness: Mapped[float] = mapped_column(Float, default=0.0)  # 配置完成度 0-1
    scope: Mapped[str] = mapped_column(String(16), default="personal", index=True)  # AgentScope
    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("classes.id"), nullable=True, index=True
    )
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)  # AgentStatus
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AgentRun(Base):
    """智能体运行记录（正式运行才落库；预演不写）。"""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True, index=True
    )
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(16), default="rule")  # AgentRunSource: llm / rule
    trace: Mapped[list] = mapped_column(JSON, default=list)  # 工具轨迹
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(64), default="")

    rating_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating_comment: Mapped[str] = mapped_column(Text, default="")
    adopted_target: Mapped[str | None] = mapped_column(String(16), nullable=True)  # script / report
    adopted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
