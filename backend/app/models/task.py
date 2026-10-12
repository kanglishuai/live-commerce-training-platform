"""任务与场次。

场次（TrainingSession）是全部业务数据的归属核心：
调研、货盘、采购、定价、脚本、装修、直播事件、订单、复盘、成绩均挂在场次上。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="personal")  # TaskMode
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)  # TaskStatus

    initial_fund_cents: Mapped[int] = mapped_column(Integer, default=5_000_000)  # 初始经营资金（分）
    market_heat: Mapped[float] = mapped_column(Float, default=5.0)  # 市场热度 1-10
    competition_level: Mapped[float] = mapped_column(Float, default=5.0)  # 竞争难度 1-10
    strict_mode: Mapped[bool] = mapped_column(Boolean, default=False)  # 严格开播门槛

    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 评分权重：{"dimensions": {"operation": 30, "process": 25, ...}, "objective_ratio": 0.6}
    weight_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # 教师布置的智能体作业：[{"agent_id": 1, "instructions": "..."}]
    agent_assignments: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class TrainingSession(Base):
    """直播场次（学生的一次完整训练）。"""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")

    status: Mapped[str] = mapped_column(String(16), default="preparing", index=True)  # SessionStatus
    fund_balance_cents: Mapped[int] = mapped_column(Integer, default=0)  # 当前经营资金余额（分）

    # 各经营环节的提交物（JSON，字段结构见 docs/API.md 各接口）
    research: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 调研纪要
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 直播策划
    script: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 脚本 {"segments": [...]}
    room_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 直播间装修

    # 实时仿真快照与 tick 控制：{"online": 0, "viewers": 0, ..., "tick_count": 0, "last_tick_at": ...}
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
