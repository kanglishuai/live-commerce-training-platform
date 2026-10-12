"""AI 岗位智能体中心。

约束（题目第 13 章）：
- 完成度 = 命名(0.2) + 职责(0.25) + 行为指令(0.35) + 工具配置(0.2)。
- 预演不写入正式业务、不落 run 记录；正式运行保留输入/输出/来源/轨迹/耗时/模型。
- 「先生成、后采纳」：只有显式 adopt 才把结果写入本人有权修改的脚本或复盘。
- 规则兜底与 LLM 输出以 source 区分；学生提交个人智能体供教师审核上架。
"""

import logging
import time

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.core import errors
from app.core.config import get_settings
from app.core.deps import CurrentUser, DbDep, assert_session_access, get_session_or_404
from app.core.enums import AgentScope, AgentStatus, Role
from app.db.base import utcnow
from app.models.agent import Agent, AgentRun
from app.models.evaluation import Report
from app.models.task import TrainingSession
from app.models.user import Klass, User
from app.schemas.agent import (
    AdoptIn,
    AdoptOut,
    AgentCreateIn,
    AgentInputIn,
    AgentOut,
    AgentPatchIn,
    AgentRunOut,
    RatingIn,
    RehearseOut,
    ReviewIn,
)
from app.schemas.common import Page
from app.services import ai
from app.prompts import templates as prompts

logger = logging.getLogger(__name__)
router = APIRouter(tags=["AI 智能体"])


def _completeness(data: dict) -> float:
    score = 0.0
    score += 0.20 if (data.get("name") or "").strip() else 0
    score += 0.25 if (data.get("duty") or "").strip() else 0
    score += 0.35 if (data.get("instructions") or "").strip() else 0
    score += 0.20 if data.get("tools") else 0
    return round(score, 2)


# 各岗位的规则兜底模板：明确标注为规则生成，不含编造数据
RULE_TEMPLATES: dict[str, str] = {
    "service": "客服处理建议（规则模板）：① 先确认问题类型（价格/成分/售后/发货）；② 按 FAQ 口径一句话回应并给出下一步动作；③ 涉及承诺（退换、时效）只引用已配置的服务条款；④ 争议升级给教师复核。",
    "select": "选品分析框架（规则模板）：① 类目热度与价格带对照；② 成本与直播价毛利空间测算；③ 引流款/利润款/形象款组合建议；④ 库存与资金占用评估。",
    "operation": "运营检查清单（规则模板）：① 货盘与定价是否覆盖三类定位；② 投流预算与预期进房量；③ 脚本环节是否覆盖开场到收尾；④ 复盘指标口径确认。",
    "control": "场控要点（规则模板）：① 按脚本节奏切换讲解商品；② 每 3-5 分钟触发一次互动（优惠券/抽奖/投票）；③ 置顶高频问题评论；④ 提示主播口播与库存变化。",
    "host": "主播话术框架（规则模板）：先共情确认需求 → 讲卖点对应痛点 → 报价对比市场价 → 给出限时权益 → 引导下单动作。",
    "teaching": "教学建议（规则模板）：把任务目标拆为可观察的岗位动作，分别设置过程证据（口播/互动/订单）与结果指标（GMV/转化/履约）。",
}


def _rule_output(agent: Agent, prompt: str) -> dict:
    template = RULE_TEMPLATES.get(agent.position_type, "（规则模板）请结合岗位职责与场次数据人工分析。")
    return {
        "result": f"【规则兜底输出·未接入大模型】针对「{prompt[:60]}」：\n{template}",
        "evidence": list(agent.knowledge_cards or []),
        "caveats": ["当前未配置大模型服务，结果由规则模板生成，仅供教学设计参考"],
    }


def _run_agent(agent: Agent, payload: AgentInputIn, session: TrainingSession | None) -> tuple[dict, str, list, int, str]:
    """执行一次智能体调用，返回 (output, source, trace, latency_ms, model)。"""
    settings = get_settings()
    context = dict(payload.context or {})
    if session is not None:
        context["session"] = {
            "id": session.id,
            "name": session.name,
            "status": session.status,
            "metrics": {
                k: (session.metrics or {}).get(k)
                for k in ("viewers", "orders", "gmv_cents", "online")
            },
            "fund_balance_cents": session.fund_balance_cents,
        }
    context["prompt"] = payload.prompt

    trace: list[dict] = [{"step": "context", "keys": sorted(context.keys())}]
    started = time.perf_counter()
    if ai.is_llm_configured():
        try:
            system, user_prompt = prompts.agent_run(agent, context)
            data, source = ai.chat_json(user_prompt, system=system)
            latency = int((time.perf_counter() - started) * 1000)
            trace.append({"step": "llm_call", "model": settings.llm_model, "latency_ms": latency})
            output = {
                "result": str(data.get("result", "")),
                "evidence": list(data.get("evidence") or []),
                "caveats": list(data.get("caveats") or []),
            }
            if not output["result"]:
                raise ValueError("LLM 输出缺少 result 字段")
            return output, source, trace, latency, settings.llm_model
        except (ai.AiUnavailable, ValueError, KeyError) as exc:
            logger.warning("智能体 LLM 运行失败，降级规则模板：%s", exc)
            trace.append({"step": "llm_failed", "error": str(exc)})
    latency = int((time.perf_counter() - started) * 1000)
    trace.append({"step": "rule_fallback"})
    return _rule_output(agent, payload.prompt), "rule", trace, latency, "rule-template"


# ---- 市场与设计台 ----

@router.get("/agents", response_model=Page[AgentOut], summary="智能体市场（内置/班级共享/个人）")
def list_agents(
    user: CurrentUser,
    db: DbDep,
    scope: str | None = None,
    position_type: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[AgentOut]:
    market = or_(
        (Agent.scope == AgentScope.BUILTIN) & (Agent.status == AgentStatus.PUBLISHED),
        (Agent.scope == AgentScope.CLASS)
        & (Agent.status == AgentStatus.PUBLISHED)
        & (Agent.class_id == user.class_id),
        Agent.owner_id == user.id,
    )
    if user.role == Role.TEACHER:
        # 教师：本班班级共享市场 + 本班学生提交的待审核队列（审核通道，19.4 场景）
        my_class_ids = select(Klass.id).where(Klass.teacher_id == user.id)
        class_market = (
            (Agent.scope == AgentScope.CLASS)
            & (Agent.status == AgentStatus.PUBLISHED)
            & Agent.class_id.in_(my_class_ids)
        )
        student_ids = select(User.id).where(User.class_id.in_(my_class_ids))
        review_queue = (
            (Agent.status == AgentStatus.PENDING)
            & (Agent.scope == AgentScope.PERSONAL)
            & Agent.owner_id.in_(student_ids)
        )
        market = or_(market, class_market, review_queue)

    elif user.role == Role.ADMIN:
        # 管理员：内置/班级市场全量 + 全部待审核 + 自己创建的
        market = or_(
            Agent.scope == AgentScope.BUILTIN,
            Agent.scope == AgentScope.CLASS,
            Agent.status == AgentStatus.PENDING,
            Agent.owner_id == user.id,
        )

    stmt = select(Agent).where(market)
    count_stmt = select(func.count(Agent.id)).where(market)
    if scope:
        stmt, count_stmt = stmt.where(Agent.scope == scope), count_stmt.where(Agent.scope == scope)
    if position_type:
        stmt, count_stmt = (
            stmt.where(Agent.position_type == position_type),
            count_stmt.where(Agent.position_type == position_type),
        )
    if keyword:
        like = f"%{keyword}%"
        stmt, count_stmt = stmt.where(Agent.name.like(like)), count_stmt.where(Agent.name.like(like))
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(Agent.id).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[AgentOut](
        items=[AgentOut.model_validate(a) for a in rows], total=total, page=page, page_size=page_size
    )


@router.post("/agents", response_model=AgentOut, summary="创建智能体（可从内置模板开始）")
def create_agent(payload: AgentCreateIn, user: CurrentUser, db: DbDep) -> AgentOut:
    data = payload.model_dump()
    template_id = data.pop("from_template_id", None)
    if template_id is not None:
        template = db.get(Agent, template_id)
        if template is None or template.scope != AgentScope.BUILTIN:
            raise errors.validation_error("模板不存在或不是内置模板", {"from_template_id": template_id})
        for key in ("duty", "instructions", "tools", "knowledge_cards", "skills", "triggers"):
            if not data.get(key) and template.__getattribute__(key):
                data[key] = getattr(template, key)
    agent = Agent(
        **data,
        scope=AgentScope.PERSONAL,
        owner_id=user.id,
        status=AgentStatus.DRAFT,
    )
    agent.completeness = _completeness(data)
    db.add(agent)
    db.commit()
    return AgentOut.model_validate(agent)


@router.get("/agents/{agent_id}", response_model=AgentOut, summary="智能体详情")
def get_agent(agent_id: int, user: CurrentUser, db: DbDep) -> AgentOut:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise errors.not_found("智能体", agent_id)
    visible = (
        agent.owner_id == user.id
        or agent.status == AgentStatus.PUBLISHED
        and (agent.scope == AgentScope.BUILTIN or agent.class_id == user.class_id)
    )
    if not visible:
        raise errors.permission_denied("无权查看该智能体")
    return AgentOut.model_validate(agent)


@router.patch("/agents/{agent_id}", response_model=AgentOut, summary="修改智能体（所有者，草稿/被驳回状态）")
def patch_agent(agent_id: int, payload: AgentPatchIn, user: CurrentUser, db: DbDep) -> AgentOut:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise errors.not_found("智能体", agent_id)
    if agent.owner_id != user.id and user.role != Role.ADMIN:
        raise errors.permission_denied("仅创建者可修改智能体")
    if agent.status in (AgentStatus.PENDING, AgentStatus.PUBLISHED):
        raise errors.AppError(
            errors.AGENT_NOT_APPROVED, f"当前状态 {agent.status} 不能直接修改（审核中/已上架）", 400
        )
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(agent, key, value)
    agent.completeness = _completeness(
        {k: getattr(agent, k) for k in ("name", "duty", "instructions", "tools")}
    )
    db.commit()
    return AgentOut.model_validate(agent)


@router.post("/agents/{agent_id}/rehearse", response_model=RehearseOut, summary="预演（不写入正式业务）")
def rehearse_agent(agent_id: int, payload: AgentInputIn, user: CurrentUser, db: DbDep) -> RehearseOut:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise errors.not_found("智能体", agent_id)
    if agent.owner_id != user.id and user.role != Role.ADMIN:
        raise errors.permission_denied("预演仅限创建者（读取当前配置，不落库）")
    session = None
    if payload.context.get("session_id"):
        session = get_session_or_404(db, int(payload.context["session_id"]))
        assert_session_access(db, user, session)
    output, source, trace, latency, model = _run_agent(agent, payload, session)
    return RehearseOut(
        output=output, source=source, trace=trace, latency_ms=latency, model=model, persist=False
    )


@router.post("/agents/{agent_id}/run", response_model=AgentRunOut, summary="正式运行（落库，含轨迹）")
def run_agent(agent_id: int, payload: AgentInputIn, user: CurrentUser, db: DbDep) -> AgentRunOut:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise errors.not_found("智能体", agent_id)
    if agent.scope == AgentScope.PERSONAL:
        if agent.owner_id != user.id and user.role != Role.ADMIN:
            raise errors.permission_denied("个人智能体仅创建者可使用")
    else:
        if agent.status != AgentStatus.PUBLISHED:
            raise errors.AppError(errors.AGENT_NOT_PUBLISHED, "该智能体尚未上架", 400)
        if agent.scope == AgentScope.CLASS and agent.class_id != user.class_id and user.role == Role.STUDENT:
            raise errors.permission_denied("该智能体仅限所属班级使用")

    session = None
    task_id = None
    if payload.context.get("session_id"):
        session = get_session_or_404(db, int(payload.context["session_id"]))
        assert_session_access(db, user, session)
        task_id = session.task_id

    output, source, trace, latency, model = _run_agent(agent, payload, session)
    run = AgentRun(
        agent_id=agent.id,
        session_id=session.id if session else None,
        task_id=task_id,
        user_id=user.id,
        input=payload.model_dump(),
        output=output,
        source=source,
        trace=trace,
        latency_ms=latency,
        model=model,
    )
    db.add(run)
    db.commit()
    return AgentRunOut.model_validate(run)


@router.get("/agent-runs", response_model=Page[AgentRunOut], summary="运行记录")
def list_runs(
    user: CurrentUser,
    db: DbDep,
    agent_id: int | None = None,
    session_id: int | None = None,
    task_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[AgentRunOut]:
    stmt = select(AgentRun)
    count_stmt = select(func.count(AgentRun.id))
    if user.role == Role.STUDENT:
        cond = AgentRun.user_id == user.id
    elif user.role == Role.TEACHER:
        from app.models.task import Task
        from app.models.user import Klass

        class_ids = select(Klass.id).where(Klass.teacher_id == user.id).scalar_subquery()
        task_ids = select(Task.id).where(Task.class_id.in_(class_ids)).scalar_subquery()
        cond = (AgentRun.user_id == user.id) | (AgentRun.task_id.in_(task_ids))
    else:
        cond = None
    if cond is not None:
        stmt, count_stmt = stmt.where(cond), count_stmt.where(cond)
    for column, value in (("agent_id", agent_id), ("session_id", session_id), ("task_id", task_id)):
        if value is not None:
            col = getattr(AgentRun, column)
            stmt, count_stmt = stmt.where(col == value), count_stmt.where(col == value)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(AgentRun.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[AgentRunOut](
        items=[AgentRunOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.post("/agent-runs/{run_id}/adopt", response_model=AdoptOut, summary="采纳结果（写入脚本/复盘）")
def adopt_run(run_id: int, payload: AdoptIn, user: CurrentUser, db: DbDep) -> AdoptOut:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise errors.not_found("运行记录", run_id)
    if run.user_id != user.id:
        raise errors.permission_denied("只能采纳本人运行的智能体结果")
    if run.session_id is None:
        raise errors.validation_error("该运行没有关联场次，无法采纳", {"run_id": run_id})
    session = get_session_or_404(db, run.session_id)
    assert_session_access(db, user, session)
    if run.adopted_target is not None:
        raise errors.AppError(errors.DUPLICATE, f"该结果已采纳到 {run.adopted_target}", 409)

    text = (run.output or {}).get("result", "")
    agent = db.get(Agent, run.agent_id)
    entry = {
        "run_id": run.id,
        "agent_id": run.agent_id,
        "agent_name": agent.name if agent else "",
        "text": text,
        "adopted_at": utcnow().isoformat(),
    }
    if payload.target == "script":
        script = dict(session.script or {})
        notes = list(script.get("adopted_notes") or [])
        notes.append(entry)
        script["adopted_notes"] = notes
        session.script = script
        applied = {"segments": len(script.get("segments") or []), "adopted_notes": len(notes)}
    else:  # report
        report = db.execute(select(Report).where(Report.session_id == session.id)).scalar_one_or_none()
        if report is None:
            raise errors.not_found("复盘报告（请先生成）", session.id)
        if report.locked:
            raise errors.AppError(errors.REPORT_LOCKED, "报告已提交锁定，不能采纳写入", 400)
        content = dict(report.content or {})
        notes = list(content.get("adopted_notes") or [])
        notes.append(entry)
        content["adopted_notes"] = notes
        report.content = content
        applied = {"adopted_notes": len(notes)}
    run.adopted_target = payload.target
    run.adopted_at = utcnow()
    db.commit()
    return AdoptOut(run_id=run.id, target=payload.target, applied_to=applied, adopted_at=run.adopted_at)


@router.post("/agent-runs/{run_id}/rating", response_model=AgentRunOut, summary="结果评分")
def rate_run(run_id: int, payload: RatingIn, user: CurrentUser, db: DbDep) -> AgentRunOut:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise errors.not_found("运行记录", run_id)
    if run.user_id != user.id and user.role != Role.ADMIN:
        raise errors.permission_denied("仅运行者可评价")
    run.rating_score = payload.score
    run.rating_comment = payload.comment
    db.commit()
    return AgentRunOut.model_validate(run)


@router.post("/agents/{agent_id}/submit", response_model=AgentOut, summary="提交审核（学生）")
def submit_agent(agent_id: int, user: CurrentUser, db: DbDep) -> AgentOut:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise errors.not_found("智能体", agent_id)
    if agent.owner_id != user.id:
        raise errors.permission_denied("仅创建者可提交审核")
    if agent.status not in (AgentStatus.DRAFT, AgentStatus.REJECTED):
        raise errors.AppError(errors.AGENT_NOT_APPROVED, f"当前状态 {agent.status} 不能提交审核", 400)
    if agent.completeness < 0.6:
        raise errors.validation_error(
            "配置完成度不足 60%，请补全职责与行为指令后再提交", {"completeness": agent.completeness}
        )
    agent.status = AgentStatus.PENDING
    db.commit()
    return AgentOut.model_validate(agent)


@router.post("/agents/{agent_id}/review", response_model=AgentOut, summary="审核智能体（教师/管理员）")
def review_agent(agent_id: int, payload: ReviewIn, user: CurrentUser, db: DbDep) -> AgentOut:
    if user.role == Role.STUDENT:
        raise errors.permission_denied("仅教师/管理员可审核")
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise errors.not_found("智能体", agent_id)
    if agent.status != AgentStatus.PENDING:
        raise errors.AppError(errors.AGENT_NOT_APPROVED, f"当前状态 {agent.status} 不在待审核队列", 400)
    agent.review_note = payload.note
    if payload.action == "approve":
        agent.status = AgentStatus.PUBLISHED
        agent.scope = AgentScope.CLASS
        if agent.class_id is None:
            owner = db.get(User, agent.owner_id) if agent.owner_id else None
            if owner is not None and owner.class_id is not None:
                agent.class_id = owner.class_id
    else:
        agent.status = AgentStatus.REJECTED
    db.commit()
    return AgentOut.model_validate(agent)
