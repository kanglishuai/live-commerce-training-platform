"""直播中接口：开播控制、仿真 tick、事件增量拉取、口播/行为/中控/回复、语音转写。

实时方案（见 探索记录.md 未知项 1）：前端以固定周期调用 tick 推进仿真，
并用 since_id 增量拉取事件流；不含 WebSocket，后续可平滑替换。
"""

import logging

import httpx
from fastapi import APIRouter, Query, Request, UploadFile
from sqlalchemy import select

from app.core import errors
from app.core.config import get_settings
from app.core.deps import (
    CurrentUser,
    DbDep,
    assert_session_access,
    get_owned_session,
    get_session_or_404,
)
from app.core.enums import ControlAction, LiveEventType, SessionStatus, SpeechSource
from app.db.base import utcnow
from app.models.commerce import SessionItem
from app.models.live import LiveEvent
from app.models.task import Task, TrainingSession
from app.schemas.live import (
    BehaviorIn,
    ControlIn,
    EventsOut,
    LiveEventOut,
    LiveStateOut,
    LiveTickOut,
    ReplyIn,
    ReplySuggestIn,
    ReplySuggestOut,
    SpeechIn,
    SpeechOut,
    TranscribeOut,
)
from app.services import ai, preflight, simulation
from app.prompts import templates as prompts

logger = logging.getLogger(__name__)
router = APIRouter(tags=["直播"])


def _latest_event_id(db: DbDep, session_id: int) -> int:
    return simulation.latest_event_id(db, session_id)


def _snapshot_out(session: TrainingSession) -> dict:
    from app.schemas.live import SnapshotOut

    return SnapshotOut.model_validate(simulation.snapshot_of(session))


def _state(db: DbDep, session: TrainingSession) -> LiveStateOut:
    return LiveStateOut(
        session_id=session.id,
        status=session.status,
        snapshot=_snapshot_out(session),
        latest_event_id=_latest_event_id(db, session.id),
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


def _system_event(db: DbDep, session: TrainingSession, text: str) -> LiveEvent:
    event = LiveEvent(
        session_id=session.id,
        type=LiveEventType.SYSTEM,
        payload={"text": text},
        source="rule",
    )
    db.add(event)
    db.flush()
    return event


# ---- 开播控制 ----

@router.post("/sessions/{session_id}/live/start", response_model=LiveStateOut, summary="开始直播")
def start_live(session_id: int, user: CurrentUser, db: DbDep) -> LiveStateOut:
    from app.services import state_machines

    session = get_owned_session(db, user, session_id)
    state_machines.assert_session_status(session, SessionStatus.PREPARING)
    task = db.get(Task, session.task_id)
    checklist = preflight.build_checklist(db, session)
    if task is not None and task.strict_mode and not checklist["passed"]:
        missing = [i["label"] for i in checklist["items"] if i["required"] and not i["passed"]]
        raise errors.AppError(
            errors.PREFLIGHT_FAILED,
            "开播检查未通过，严格任务不允许直接开播：" + "、".join(missing),
            400,
            {"missing": missing, "checklist": checklist["items"]},
        )
    session.status = SessionStatus.LIVE
    session.started_at = utcnow()
    first_item = db.execute(
        select(SessionItem)
        .where(SessionItem.session_id == session.id, SessionItem.status == "listed")
        .order_by(SessionItem.sort)
        .limit(1)
    ).scalar_one_or_none()
    session.metrics = {
        **(session.metrics or {}),
        "current_item_id": first_item.id if first_item else None,
    }
    _system_event(db, session, "直播开始")
    db.commit()
    return _state(db, session)


@router.post("/sessions/{session_id}/live/pause", response_model=LiveStateOut, summary="暂停直播")
def pause_live(session_id: int, user: CurrentUser, db: DbDep) -> LiveStateOut:
    from app.services import state_machines

    session = get_owned_session(db, user, session_id)
    state_machines.assert_transition(
        state_machines.SESSION_TRANSITIONS, session.status, SessionStatus.PAUSED, "场次"
    )
    session.status = SessionStatus.PAUSED
    _system_event(db, session, "直播已暂停")
    db.commit()
    return _state(db, session)


@router.post("/sessions/{session_id}/live/resume", response_model=LiveStateOut, summary="恢复直播")
def resume_live(session_id: int, user: CurrentUser, db: DbDep) -> LiveStateOut:
    from app.services import state_machines

    session = get_owned_session(db, user, session_id)
    state_machines.assert_transition(
        state_machines.SESSION_TRANSITIONS, session.status, SessionStatus.LIVE, "场次"
    )
    session.status = SessionStatus.LIVE
    _system_event(db, session, "直播已恢复")
    db.commit()
    return _state(db, session)


@router.post("/sessions/{session_id}/live/stop", response_model=LiveStateOut, summary="下播（进入履约与复盘）")
def stop_live(session_id: int, user: CurrentUser, db: DbDep) -> LiveStateOut:
    from app.services import state_machines

    session = get_owned_session(db, user, session_id)
    state_machines.assert_transition(
        state_machines.SESSION_TRANSITIONS, session.status, SessionStatus.ENDED, "场次"
    )
    session.status = SessionStatus.ENDED
    session.ended_at = utcnow()
    if session.metrics:
        session.metrics = {**session.metrics, "last_tick_at": None}
    _system_event(db, session, "直播已结束，请完成订单履约与售后后提交复盘")
    db.commit()
    return _state(db, session)


@router.post("/sessions/{session_id}/live/tick", response_model=LiveTickOut, summary="推进仿真周期")
def live_tick(session_id: int, user: CurrentUser, db: DbDep) -> LiveTickOut:
    get_owned_session(db, user, session_id)  # 权限校验
    result = simulation.tick(db, session_id)
    session = get_session_or_404(db, session_id)
    db.commit()
    return LiveTickOut(
        session_id=session.id,
        status=result["status"],
        snapshot=_snapshot_out(session),
        new_events=[LiveEventOut.model_validate(e) for e in result["new_events"]],
        latest_event_id=result["latest_event_id"],
    )


@router.get("/sessions/{session_id}/live/state", response_model=LiveStateOut, summary="直播状态与快照")
def live_state(session_id: int, user: CurrentUser, db: DbDep) -> LiveStateOut:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    return _state(db, session)


@router.get("/sessions/{session_id}/live/events", response_model=EventsOut, summary="事件增量拉取")
def live_events(
    session_id: int,
    user: CurrentUser,
    db: DbDep,
    since_id: int = Query(0, ge=0),
    type: LiveEventType | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> EventsOut:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    stmt = select(LiveEvent).where(LiveEvent.session_id == session.id, LiveEvent.id > since_id)
    if type is not None:
        stmt = stmt.where(LiveEvent.type == type)
    rows = db.execute(stmt.order_by(LiveEvent.id).limit(limit)).scalars().all()
    return EventsOut(
        events=[LiveEventOut.model_validate(e) for e in rows],
        latest_event_id=_latest_event_id(db, session.id),
    )


# ---- 直播过程记录 ----

def _require_live(session: TrainingSession) -> None:
    if session.status != SessionStatus.LIVE:
        raise errors.AppError(
            errors.SESSION_NOT_LIVE,
            f"场次状态为 {session.status}，该操作仅直播中可用",
            400,
            {"current": session.status},
        )


@router.post("/sessions/{session_id}/live/speech", response_model=SpeechOut, summary="提交口播识别文本")
def submit_speech(session_id: int, payload: SpeechIn, user: CurrentUser, db: DbDep) -> SpeechOut:
    session = get_owned_session(db, user, session_id)
    _require_live(session)
    event = LiveEvent(
        session_id=session.id,
        type=LiveEventType.SPEECH,
        payload={"text": payload.text, "chars": len(payload.text)},
        source=str(payload.source),
    )
    db.add(event)
    db.flush()

    # 敏感词检查：命中则写入违规事件（不阻断口播保存）
    sensitive = [w for w in ((session.room_config or {}).get("sensitive_words") or []) if w]
    hit = [w for w in sensitive if w in payload.text]
    messages = [f"口播已保存（来源：{payload.source}）"]
    if hit:
        db.add(
            LiveEvent(
                session_id=session.id,
                type=LiveEventType.VIOLATION,
                payload={"text": payload.text, "words": hit, "speech_event_id": event.id},
                source="rule",
            )
        )
        messages.append(f"命中敏感词：{'、'.join(hit)}，已记录违规")
    db.commit()
    return SpeechOut(event=LiveEventOut.model_validate(event), violation=bool(hit), messages=messages)


@router.post("/sessions/{session_id}/live/behavior", response_model=LiveEventOut, summary="提交出镜行为采样")
def submit_behavior(session_id: int, payload: BehaviorIn, user: CurrentUser, db: DbDep) -> LiveEventOut:
    session = get_owned_session(db, user, session_id)
    _require_live(session)
    event = LiveEvent(
        session_id=session.id,
        type=LiveEventType.BEHAVIOR,
        payload={"face_detected": payload.face_detected, "smile_coef": payload.smile_coef},
        source="client_local",  # 终端侧采样：视频帧不上传服务器
    )
    db.add(event)
    db.commit()
    return LiveEventOut.model_validate(event)


@router.post("/sessions/{session_id}/live/control", response_model=LiveEventOut, summary="直播中控动作")
def submit_control(session_id: int, payload: ControlIn, user: CurrentUser, db: DbDep) -> LiveEventOut:
    session = get_owned_session(db, user, session_id)
    _require_live(session)
    detail = dict(payload.payload or {})
    action = str(payload.action)

    if action == ControlAction.SWITCH_ITEM:
        item_id = detail.get("item_id")
        item = db.get(SessionItem, int(item_id)) if item_id else None
        if item is None or item.session_id != session.id:
            raise errors.validation_error("切换的商品不在本场货盘中", {"item_id": item_id})
        if item.status != "listed":
            raise errors.AppError(
                errors.STATE_TRANSITION_INVALID, "该商品未上架，不能切换讲解", 400
            )
        session.metrics = {**(session.metrics or {}), "current_item_id": item.id}
        detail["item_name"] = item.title or item.custom_name
    elif action == ControlAction.ANNOUNCEMENT and not (detail.get("text") or "").strip():
        raise errors.validation_error("公告内容不能为空", {"action": action})
    elif action in (ControlAction.PUSH_COUPON, ControlAction.SECKILL, ControlAction.LOTTERY):
        if not (detail.get("text") or detail.get("promo_id")):
            raise errors.validation_error("该玩法需要提供文案或关联促销", {"action": action})

    event = LiveEvent(
        session_id=session.id,
        type=LiveEventType.CONTROL,
        payload={"action": action, "detail": detail},
        source="manual",
    )
    db.add(event)
    db.commit()
    return LiveEventOut.model_validate(event)


@router.post("/sessions/{session_id}/live/replies", response_model=LiveEventOut, summary="主播回复评论")
def submit_reply(session_id: int, payload: ReplyIn, user: CurrentUser, db: DbDep) -> LiveEventOut:
    session = get_owned_session(db, user, session_id)
    _require_live(session)
    comment = db.get(LiveEvent, payload.comment_event_id)
    if comment is None or comment.session_id != session.id or comment.type != LiveEventType.COMMENT:
        raise errors.validation_error("评论不存在或不属于本场", {"comment_event_id": payload.comment_event_id})
    event = LiveEvent(
        session_id=session.id,
        type=LiveEventType.REPLY,
        payload={
            "comment_event_id": comment.id,
            "comment_text": (comment.payload or {}).get("text", ""),
            "text": payload.text,
        },
        source="manual",
    )
    db.add(event)
    db.commit()
    return LiveEventOut.model_validate(event)


REPLY_RULES = [
    ("价格", "亲，这款是本场直播专享价，还叠加了优惠券，下单即享哦~"),
    ("成分", "亲，成分表在商品详情第 2 张图，主要成分都标注了，敏感肌建议先做局部试用~"),
    ("退货", "亲，支持七天无理由退换，运费险已包含，放心拍~"),
    ("发货", "亲，下单后 48 小时内发货，物流信息会实时同步~"),
    ("库存", "亲，库存有限哦，现在下单锁定名额~"),
]


@router.post(
    "/sessions/{session_id}/live/replies/suggest", response_model=ReplySuggestOut, summary="AI 回复建议（不落库）"
)
def suggest_reply(
    session_id: int, payload: ReplySuggestIn, user: CurrentUser, db: DbDep
) -> ReplySuggestOut:
    session = get_session_or_404(db, session_id)
    assert_session_access(db, user, session)
    comment = db.get(LiveEvent, payload.comment_event_id)
    if comment is None or comment.session_id != session.id or comment.type != LiveEventType.COMMENT:
        raise errors.validation_error("评论不存在或不属于本场", {"comment_event_id": payload.comment_event_id})
    comment_text = (comment.payload or {}).get("text", "")
    current_item_id = (session.metrics or {}).get("current_item_id")
    item = db.get(SessionItem, current_item_id) if current_item_id else None
    context = {
        "comment": comment_text,
        "persona": (comment.payload or {}).get("persona"),
        "current_item": None
        if item is None
        else {
            "name": item.title or item.custom_name,
            "live_price_cents": item.live_price_cents,
            "stock": item.stock,
            "selling_points": item.selling_points,
        },
        "faq": (session.room_config or {}).get("faq") or [],
    }

    if ai.is_llm_configured():
        try:
            data, source = ai.chat_json(prompts.reply_suggest(context), system=prompts.REPLY_SYSTEM)
            text = str(data.get("reply") or "").strip()
            if text:
                return ReplySuggestOut(text=text, source=source)
        except (ai.AiUnavailable, ValueError, KeyError) as exc:
            logger.warning("回复建议 LLM 失败，降级规则：%s", exc)

    text = "亲，感谢关注，主播马上为你解答~"
    for keyword, reply in REPLY_RULES:
        if keyword in comment_text:
            text = reply
            break
    else:
        if item is not None:
            points = "、".join((item.selling_points or [])[:2])
            text = f"亲，这款「{item.title or item.custom_name}」{points}，现在直播价 {item.live_price_cents / 100:.1f} 元，很划算哦~"
    return ReplySuggestOut(text=text, source="rule")


# ---- 语音转写（服务端 ASR，可选）----

@router.post("/speech/transcribe", response_model=TranscribeOut, summary="音频转写（可选外部 ASR）")
async def transcribe(request: Request, file: UploadFile) -> TranscribeOut:
    settings = get_settings()
    if not (settings.asr_base_url and settings.asr_api_key):
        raise errors.AppError(
            errors.ASR_NOT_CONFIGURED,
            "未配置服务端语音识别，请使用浏览器识别或手动补录（前端已内置降级）",
            501,
        )
    content = await file.read()
    try:
        resp = httpx.post(
            settings.asr_base_url,
            headers={"Authorization": f"Bearer {settings.asr_api_key}"},
            files={"file": (file.filename or "audio.webm", content, file.content_type or "audio/webm")},
            timeout=settings.asr_timeout_seconds,
        )
        resp.raise_for_status()
        text = str(resp.json().get("text") or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ASR 调用失败：%s", exc)
        raise errors.AppError(
            errors.EXTERNAL_SERVICE_UNAVAILABLE, f"语音识别服务调用失败：{exc}", 502
        ) from exc
    return TranscribeOut(text=text, source=str(SpeechSource.SERVER_ASR))
