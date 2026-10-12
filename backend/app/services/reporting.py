"""复盘报告生成：规则兜底 + LLM 可选增强。

题目第 11 章要求：模型不可用时生成“明确标识的规则汇总”，避免把规则文本伪装成 AI 结果。
因此 Report.source 字段恒为 "rule" 或 "llm"，前端与教师界面据此展示来源标签。
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.enums import ReportSource
from app.db.base import utcnow
from app.models.evaluation import Report
from app.models.task import Task, TrainingSession
from app.services import ai, metrics
from app.prompts import templates as prompts

logger = logging.getLogger(__name__)


def _fmt_yuan(cents: int) -> str:
    return f"{cents / 100:,.2f} 元"


def build_rule_content(db: OrmSession, session: TrainingSession) -> dict:
    """规则兜底汇总：全部结论来自可核对的过程数据。"""
    task = db.get(Task, session.task_id)
    overview, _ = metrics.build(db, session, "overview")
    sales, _ = metrics.build(db, session, "sales")
    traffic, _ = metrics.build(db, session, "traffic")

    goal = (session.plan or {}).get("goals") or {}
    goal_gmv = int(goal.get("gmv_cents", 0) or 0)
    achieved = overview["gmv_cents"] >= goal_gmv if goal_gmv else None

    highlights: list[str] = []
    issues: list[str] = []
    risks: list[str] = []
    next_actions: list[str] = []

    if overview["gmv_cents"] > 0:
        highlights.append(f"本场达成成交 {overview['orders']} 单，GMV {_fmt_yuan(overview['gmv_cents'])}")
    if overview["click_rate"] >= 0.08:
        highlights.append(f"商品点击率 {overview['click_rate']:.1%}，货盘吸引力较好")
    if overview["interaction_rate"] >= 0.3:
        highlights.append(f"互动率 {overview['interaction_rate']:.1%}，直播间氛围活跃")
    if not highlights:
        highlights.append("完成了从准备到开播的完整流程（本场经营数据较少）")

    if goal_gmv and not achieved:
        issues.append(
            f"GMV 目标 {_fmt_yuan(goal_gmv)} 未达成（实际 {_fmt_yuan(overview['gmv_cents'])}）"
        )
    if overview["conversion_rate"] and overview["conversion_rate"] < 0.03:
        issues.append(f"转化率仅 {overview['conversion_rate']:.1%}，讲解与促单环节可加强")
    if overview["peak_online"] < 20:
        issues.append("峰值在线偏低，流量获取不足，可评估投流预算与开播时段")
    if overview["refund_rate"] > 0.1:
        issues.append(f"退款率 {overview['refund_rate']:.1%} 偏高，需复盘商品描述与售后话术")
    if not issues:
        issues.append("未发现显著问题项（样本有限，建议对照目标自行核对）")

    if overview["violations"] > 0:
        risks.append(f"出现 {overview['violations']} 次敏感词违规，需规范直播话术")
    if overview["ship_settled"] < overview["orders"]:
        risks.append("存在未完成履约的订单，提交复盘前必须处理完毕")
    if traffic["roas"] is not None and traffic["roas"] < 1:
        risks.append(f"投流 ROAS 为 {traffic['roas']}，投入产出倒挂，需优化投放策略")
    if not risks:
        risks.append("本场未发现合规与履约风险")

    if overview["orders"] == 0:
        next_actions.append("下一场提升开播前脚本完整度，确保讲解覆盖每款上架商品")
    if overview["click_rate"] < 0.08:
        next_actions.append("优化主图与直播价吸引力，对比同类目价格带")
    if overview["conversion_rate"] < 0.05:
        next_actions.append("增加限时优惠与逼单话术，缩短决策链路")
    if not traffic["channels"]:
        next_actions.append("配置短视频预热或信息流投放，验证不同渠道的进房质量")
    if not next_actions:
        next_actions.append("保持当前货盘结构，尝试提升客单价与连带率")

    top_items = sales["item_contribution"][:3]
    sales_line = "、".join(f"{i['name']}（{_fmt_yuan(i['amount_cents'])}）" for i in top_items) or "无成交商品"

    return {
        "sections": [
            {
                "key": "goal",
                "title": "目标达成",
                "summary": (
                    f"任务目标 GMV {_fmt_yuan(goal_gmv)}，实际 {_fmt_yuan(overview['gmv_cents'])}"
                    if goal_gmv
                    else f"实际 GMV {_fmt_yuan(overview['gmv_cents'])}（本场未设置目标）"
                ),
                "bullets": [
                    f"访客 {overview['viewers']} 人，峰值在线 {overview['peak_online']} 人",
                    f"成交 {overview['orders']} 单，客单价 {_fmt_yuan(overview['aov_cents'])}",
                ],
            },
            {
                "key": "sales",
                "title": "货盘与定价",
                "summary": f"成交贡献 Top：{sales_line}",
                "bullets": [
                    f"商品点击 {overview['item_clicks']} 次，点击率 {overview['click_rate']:.1%}",
                    f"转化率 {overview['conversion_rate']:.1%}",
                ],
            },
            {
                "key": "traffic",
                "title": "流量与投放",
                "summary": f"投流花费 {_fmt_yuan(traffic['ad_spend_cents'])}，渠道 {len(traffic['channels'])} 个",
                "bullets": [
                    f"估算自然进房 {traffic['estimated_organic_viewers']} 人 / 投流进房 {traffic['estimated_ad_viewers']} 人",
                    f"ROAS：{traffic['roas'] if traffic['roas'] is not None else '未投放'}",
                ],
            },
            {
                "key": "compliance",
                "title": "合规与舆情",
                "summary": f"敏感词违规 {overview['violations']} 次",
                "bullets": [f"互动率 {overview['interaction_rate']:.1%}，评论互动计入过程评价"],
            },
            {
                "key": "fulfillment",
                "title": "履约与售后",
                "summary": f"已完结订单 {overview['ship_settled']}/{overview['orders']}，退款订单 {overview['refund_orders']} 单",
                "bullets": [f"退款率 {overview['refund_rate']:.1%}"],
            },
        ],
        "overview": (
            f"本场为「{task.title if task else '实训'}」的直播训练，"
            f"累计观看 {overview['viewers']} 人，产生 {overview['orders']} 笔模拟订单。"
        ),
        "highlights": highlights,
        "issues": issues,
        "risks": risks,
        "next_actions": next_actions,
        "data_source": "系统过程数据汇总（规则生成）",
    }


def generate(db: OrmSession, session: TrainingSession) -> Report:
    """生成/重新生成复盘报告。LLM 可用则增强，不可用则规则兜底并明确标识。"""
    content = build_rule_content(db, session)
    source = str(ReportSource.RULE)

    if ai.is_llm_configured():
        try:
            overview, _ = metrics.build(db, session, "overview")
            sales, _ = metrics.build(db, session, "sales")
            traffic, _ = metrics.build(db, session, "traffic")
            context = {"overview": overview, "sales": sales, "traffic": traffic}
            data, source = ai.chat_json(
                prompts.report_analysis(context), system=prompts.REPORT_SYSTEM
            )
            content.update(
                {
                    "overview": str(data.get("overview", content["overview"])),
                    "highlights": list(data.get("highlights") or content["highlights"]),
                    "issues": list(data.get("issues") or content["issues"]),
                    "risks": list(data.get("risks") or content["risks"]),
                    "next_actions": list(data.get("next_actions") or content["next_actions"]),
                    "data_source": "大模型基于系统过程数据生成",
                }
            )
        except (ai.AiUnavailable, ValueError, KeyError) as exc:
            logger.warning("复盘报告 LLM 生成失败，降级为规则汇总：%s", exc)
            source = str(ReportSource.RULE)

    report = db.execute(
        select(Report).where(Report.session_id == session.id)
    ).scalar_one_or_none()
    if report is None:
        report = Report(session_id=session.id)
        db.add(report)
    report.content = content
    report.source = source
    report.generated_at = utcnow()
    db.flush()
    return report
