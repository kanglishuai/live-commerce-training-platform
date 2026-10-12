"""全局枚举：与 docs/DATABASE.md、docs/API.md 附录中的取值表保持一致。

数据库中以字符串存储（便于加值不改表），接口层用这些枚举做校验。
"""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class TaskStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class TaskMode(StrEnum):
    PERSONAL = "personal"
    TEAM = "team"


class SessionStatus(StrEnum):
    """场次状态：准备 → 直播 ⇄ 暂停 → 下播 → 已提交（复盘提交后锁定）"""

    PREPARING = "preparing"
    LIVE = "live"
    PAUSED = "paused"
    ENDED = "ended"
    SUBMITTED = "submitted"


class ItemRole(StrEnum):
    """货盘定位：引流款 / 利润款 / 形象款"""

    TRAFFIC = "traffic"
    PROFIT = "profit"
    IMAGE = "image"


class ItemStatus(StrEnum):
    EDITING = "editing"
    LISTED = "listed"


class TeamPosition(StrEnum):
    HOST = "host"
    OPERATION = "operation"
    CONTROL = "control"
    SERVICE = "service"
    SELECT = "select"
    AD = "ad"


class ScriptStage(StrEnum):
    OPENING = "opening"
    WARMUP = "warmup"
    EXPLAIN = "explain"
    INTERACT = "interact"
    PUSH = "push"
    TRANSITION = "transition"
    CLOSING = "closing"


class PromotionType(StrEnum):
    COUPON = "coupon"
    FULL_REDUCTION = "full_reduction"
    SECKILL = "seckill"
    GIFT = "gift"
    LOTTERY = "lottery"
    GROUP_BUY = "group_buy"


class PromotionStatus(StrEnum):
    ACTIVE = "active"
    STOPPED = "stopped"


class AdChannel(StrEnum):
    SHORT_VIDEO = "short_video"
    FEED = "feed"
    RESERVATION = "reservation"
    SOCIAL = "social"


class AdObjective(StrEnum):
    EXPOSURE = "exposure"
    CLICK = "click"
    ENTER_ROOM = "enter_room"
    ORDER = "order"


class AdStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    STOPPED = "stopped"


class LiveEventType(StrEnum):
    METRIC = "metric"
    SPEECH = "speech"
    BEHAVIOR = "behavior"
    COMMENT = "comment"
    REPLY = "reply"
    CONTROL = "control"
    ORDER = "order"
    VIOLATION = "violation"
    AI_DECISION = "ai_decision"
    SYSTEM = "system"


class SpeechSource(StrEnum):
    SERVER_ASR = "server_asr"
    BROWSER_ASR = "browser_asr"
    MANUAL = "manual"


class ControlAction(StrEnum):
    SWITCH_ITEM = "switch_item"
    PUSH_COUPON = "push_coupon"
    SECKILL = "seckill"
    LOTTERY = "lottery"
    ANNOUNCEMENT = "announcement"
    POLL = "poll"
    PIN_COMMENT = "pin_comment"
    FAN_BENEFIT = "fan_benefit"


class OrderStatus(StrEnum):
    PENDING_SHIP = "pending_ship"
    SHIPPING = "shipping"
    SIGNED = "signed"
    CLOSED = "closed"


class LogisticsNode(StrEnum):
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    DELIVERING = "delivering"
    SIGNED = "signed"
    REJECTED = "rejected"


class AfterSaleType(StrEnum):
    REFUND = "refund"
    RETURN = "return"
    EXCHANGE = "exchange"
    COMPLAINT = "complaint"
    OVERSELL = "oversell"
    DELAY = "delay"


class AfterSaleStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    RETURNED = "returned"
    SCORED = "scored"


class ReportSource(StrEnum):
    """报告来源：llm=大模型生成；rule=规则兜底（必须明确标识，不得伪装成 AI 结果）"""

    LLM = "llm"
    RULE = "rule"


class FundTxnType(StrEnum):
    PURCHASE = "purchase"
    AD_SPEND = "ad_spend"
    SALES_INCOME = "sales_income"
    REFUND = "refund"
    ADJUST = "adjust"


class AgentScope(StrEnum):
    BUILTIN = "builtin"
    CLASS = "class"
    PERSONAL = "personal"


class AgentStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"


class AgentPosition(StrEnum):
    SELECT = "select"
    OPERATION = "operation"
    CONTROL = "control"
    SERVICE = "service"
    HOST = "host"
    TEACHING = "teaching"


class AgentRunSource(StrEnum):
    LLM = "llm"
    RULE = "rule"


class CompetitionMetric(StrEnum):
    GMV = "gmv"
    PROFIT = "profit"
    CONVERSION = "conversion"
    COMPLIANCE = "compliance"
    INTERACTION = "interaction"
    FULFILLMENT = "fulfillment"
    COMPREHENSIVE = "comprehensive"
