"""状态机：场次 / 订单 / 物流 / 售后 的状态迁移约束。

所有迁移必须经过这里校验，禁止不合理回退（题目第 10 章：系统对终态进行约束，
防止重复推进或状态回退）。
"""

from typing import Any

from app.core import errors
from app.models.task import TrainingSession

SESSION_TRANSITIONS: dict[str, set[str]] = {
    "preparing": {"live"},
    "live": {"paused", "ended"},
    "paused": {"live", "ended"},
    # submitted → ended：教师退回复盘后，学生可继续完善并重新提交
    "ended": {"submitted"},
    "submitted": {"ended"},
}

ORDER_TRANSITIONS: dict[str, set[str]] = {
    "pending_ship": {"shipping", "closed"},
    "shipping": {"signed", "closed"},
    "signed": {"closed"},
    "closed": set(),
}

# 物流节点顺序推进；拒收只能发生在运输中/派送中
LOGISTICS_TRANSITIONS: dict[str, set[str]] = {
    "picked_up": {"in_transit", "rejected"},
    "in_transit": {"delivering", "rejected"},
    "delivering": {"signed", "rejected"},
    "signed": set(),
    "rejected": set(),
}

AFTER_SALE_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"approved", "rejected"},
    "approved": {"closed"},
    "rejected": {"closed"},
    "closed": set(),
}


def assert_transition(
    transitions: dict[str, set[str]],
    current: str,
    target: str,
    entity: str,
    context: dict[str, Any] | None = None,
) -> None:
    allowed = transitions.get(current, set())
    if target not in allowed:
        raise errors.AppError(
            errors.STATE_TRANSITION_INVALID,
            f"{entity}不允许从 {current} 迁移到 {target}",
            400,
            {"current": current, "target": target, "allowed": sorted(allowed), **(context or {})},
        )


def assert_session_status(session: TrainingSession, *allowed: str) -> None:
    if session.status not in allowed:
        raise errors.AppError(
            errors.STATE_TRANSITION_INVALID,
            f"当前场次状态为 {session.status}，该操作要求状态：{'/'.join(allowed)}",
            400,
            {"current": session.status, "allowed": list(allowed)},
        )
