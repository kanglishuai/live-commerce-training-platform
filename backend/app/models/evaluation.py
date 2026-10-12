"""复盘报告、成绩、竞赛。

约束（对应题目第 10/12 章）：
- 未完成履约/售后的场次不能提交复盘；提交后报告进入只读（locked）。
- 成绩保留评分权重与评分时间，保证复查口径一致。
- AI 报告在模型不可用时降级为规则汇总，source 字段明确标识。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), unique=True, index=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict)  # {"sections": [...]}
    source: Mapped[str] = mapped_column(String(16), default="rule")  # ReportSource: llm / rule
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    improvement_plan: Mapped[str] = mapped_column(Text, default="")  # 学生填写的改进措施
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)  # ReportStatus
    locked: Mapped[bool] = mapped_column(Boolean, default=False)  # 提交后锁定
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), unique=True, index=True)
    objective_score: Mapped[float] = mapped_column(Float, default=0.0)
    objective_detail: Mapped[dict] = mapped_column(JSON, default=dict)  # 各维度得分与依据
    subjective_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    comprehensive_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    weights: Mapped[dict] = mapped_column(JSON, default=dict)  # 评分时的权重快照
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Competition(Base):
    """竞赛活动：相同初始条件下按经营结果形成排行榜。"""

    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    metric: Mapped[str] = mapped_column(String(32), default="comprehensive")  # CompetitionMetric
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="running")  # draft / running / closed
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
