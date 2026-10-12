"""资金账本：一切余额变化必须经 apply_fund_txn，保证流水可审计。

余额不足时显式报 INSUFFICIENT_FUNDS（不静默放行）。
并发场景（MySQL）用 SELECT ... FOR UPDATE 锁行；SQLite 测试环境忽略该子句。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core import errors
from app.core.enums import FundTxnType
from app.models.commerce import FundTxn
from app.models.task import TrainingSession


def lock_session(db: OrmSession, session_id: int) -> TrainingSession:
    """锁定场次行（资金操作前调用），保证并发下余额一致。"""
    session = db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id).with_for_update()
    ).scalar_one_or_none()
    if session is None:
        raise errors.not_found("场次", session_id)
    return session


def apply_fund_txn(
    db: OrmSession,
    session: TrainingSession,
    txn_type: FundTxnType | str,
    amount_cents: int,
    *,
    ref_type: str | None = None,
    ref_id: int | None = None,
    note: str = "",
    allow_negative: bool = False,
) -> FundTxn:
    """写入一条资金流水。amount_cents 为有符号值：负数为支出。

    allow_negative=True 仅用于退款等“应退必退”场景（余额允许为负，表示应付）。
    """
    if amount_cents < 0 and not allow_negative and session.fund_balance_cents + amount_cents < 0:
        raise errors.AppError(
            errors.INSUFFICIENT_FUNDS,
            f"经营资金不足：本次需要 {-amount_cents / 100:.2f} 元，当前余额 {session.fund_balance_cents / 100:.2f} 元",
            400,
            {
                "required_cents": -amount_cents,
                "balance_cents": session.fund_balance_cents,
                "txn_type": str(txn_type),
            },
        )
    session.fund_balance_cents += amount_cents
    txn = FundTxn(
        session_id=session.id,
        type=str(txn_type),
        amount_cents=amount_cents,
        balance_after_cents=session.fund_balance_cents,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
    )
    db.add(txn)
    db.flush()
    return txn
