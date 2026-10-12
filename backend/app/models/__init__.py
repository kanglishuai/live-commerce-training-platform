"""模型注册表：集中导入，保证 Base.metadata 完整（create_all / 迁移依赖此处）。"""

from app.models.agent import Agent, AgentRun
from app.models.commerce import AdPlan, FundTxn, Product, Promotion, Purchase, SessionItem
from app.models.evaluation import Competition, Report, Score
from app.models.live import AfterSale, LiveEvent, Order
from app.models.task import Task, TrainingSession
from app.models.user import Klass, Team, TeamMember, User

__all__ = [
    "AdPlan",
    "AfterSale",
    "Agent",
    "AgentRun",
    "Competition",
    "FundTxn",
    "Klass",
    "LiveEvent",
    "Order",
    "Product",
    "Promotion",
    "Purchase",
    "Report",
    "Score",
    "SessionItem",
    "Task",
    "Team",
    "TeamMember",
    "TrainingSession",
    "User",
]
