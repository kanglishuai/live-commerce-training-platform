"""统一错误：业务错误码 + 异常类型。

接口错误响应固定为 {"code": "...", "message": "...", "context": {...}}，
错误码全集见 docs/API.md 附录 B。
"""

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.context = context or {}
        super().__init__(f"{code}: {message}")


# ---- 错误码常量（与文档同步维护）----
AUTH_REQUIRED = "AUTH_REQUIRED"
INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
PERMISSION_DENIED = "PERMISSION_DENIED"
NOT_FOUND = "NOT_FOUND"
DUPLICATE = "DUPLICATE"
VALIDATION_ERROR = "VALIDATION_ERROR"
INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
STATE_TRANSITION_INVALID = "STATE_TRANSITION_INVALID"
PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
SESSION_NOT_LIVE = "SESSION_NOT_LIVE"
TICK_TOO_FREQUENT = "TICK_TOO_FREQUENT"
REPORT_LOCKED = "REPORT_LOCKED"
FULFILLMENT_INCOMPLETE = "FULFILLMENT_INCOMPLETE"
AGENT_NOT_PUBLISHED = "AGENT_NOT_PUBLISHED"
AGENT_NOT_APPROVED = "AGENT_NOT_APPROVED"
EXTERNAL_SERVICE_UNAVAILABLE = "EXTERNAL_SERVICE_UNAVAILABLE"
ASR_NOT_CONFIGURED = "ASR_NOT_CONFIGURED"
EXPORT_NOT_IMPLEMENTED = "EXPORT_NOT_IMPLEMENTED"
INTERNAL_ERROR = "INTERNAL_ERROR"


def not_found(what: str, ident: Any) -> AppError:
    return AppError(NOT_FOUND, f"{what} 不存在：{ident}", 404, {"resource": what, "id": ident})


def permission_denied(message: str = "无权访问该资源") -> AppError:
    return AppError(PERMISSION_DENIED, message, 403)


def validation_error(message: str, context: dict[str, Any] | None = None) -> AppError:
    return AppError(VALIDATION_ERROR, message, 422, context)
