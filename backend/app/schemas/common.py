"""通用模式：时间序列化（UTC + Z）、ORM 基类、分页、错误体。"""

from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, PlainSerializer

T = TypeVar("T")


def _to_utc_z(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat(timespec="seconds") + "Z"


# 所有对外时间统一为 UTC ISO8601（带 Z）；数据库存 UTC naive
UtcDatetime = Annotated[
    datetime, PlainSerializer(_to_utc_z, return_type=str | None, when_used="json")
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20


class ErrorOut(BaseModel):
    code: str
    message: str
    context: dict = {}

    model_config = ConfigDict(json_schema_extra={
        "example": {"code": "INSUFFICIENT_FUNDS", "message": "经营资金不足", "context": {"required_cents": 120000, "balance_cents": 90000}}
    })


class OkOut(BaseModel):
    ok: bool = True
    detail: str = ""
