"""开播检查：把任务要求转化为逐项核验清单。

区分「必须完成项」与「建议项」；每项给出缺失原因与返回入口。
严格任务（task.strict_mode）下未通过清单将阻断开播，普通练习仅提示。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models.commerce import AdPlan, Purchase, SessionItem
from app.models.task import Task, TrainingSession

# key, 中文标签, 是否必须项, 返回入口
CHECK_DEFS: list[tuple[str, str, bool, str]] = [
    ("research", "调研纪要", True, "research"),
    ("cart", "货盘商品", True, "cart"),
    ("role_structure", "货盘定位结构（引流款 + 利润款）", True, "cart"),
    ("purchase", "商品采购", True, "purchase"),
    ("pricing", "定价设置", True, "pricing"),
    ("plan", "直播策划", False, "plan"),
    ("script", "直播脚本", True, "script"),
    ("ad", "流量推广计划", False, "ad"),
    ("room", "直播间装修", True, "room"),
]


def build_checklist(db: OrmSession, session: TrainingSession) -> dict:
    task = db.get(Task, session.task_id)
    strict_mode = bool(task.strict_mode) if task else False

    research = session.research or {}
    items = db.execute(
        select(SessionItem).where(SessionItem.session_id == session.id)
    ).scalars().all()
    listed = [i for i in items if i.status == "listed"]
    roles = {i.role for i in listed}
    purchases = db.execute(
        select(Purchase).where(Purchase.session_id == session.id)
    ).scalars().all()
    purchased_item_ids = {p.item_id for p in purchases}
    ad_plans = db.execute(
        select(AdPlan).where(AdPlan.session_id == session.id)
    ).scalars().all()
    plan = session.plan or {}
    script = session.script or {}
    segments = script.get("segments") or []
    room = session.room_config or {}

    results: dict[str, tuple[bool, str]] = {
        "research": (
            bool(research.get("target_audience") and research.get("reasons")),
            "需填写目标人群与选品理由",
        ),
        "cart": (len(listed) >= 1, "至少 1 款商品已加入货盘并上架"),
        "role_structure": (
            {"traffic", "profit"}.issubset(roles),
            "货盘需同时包含引流款与利润款定位",
        ),
        "purchase": (
            len(listed) >= 1 and all(i.id in purchased_item_ids for i in listed),
            "上架商品需全部完成采购（库存与资金随之变化）",
        ),
        "pricing": (
            len(listed) >= 1 and all(i.live_price_cents > 0 for i in listed),
            "上架商品需设置直播价",
        ),
        "plan": (bool(plan.get("theme")), "建议填写直播主题与目标"),
        "script": (
            len(segments) >= 1 and any((s.get("speech") or "").strip() for s in segments),
            "至少 1 个脚本段落且包含口播内容",
        ),
        "ad": (len(ad_plans) >= 1, "建议配置至少 1 条投流计划以获取自然流量之外的观众"),
        "room": (
            bool(room.get("title")) and bool((room.get("canvas") or {}).get("elements")),
            "需设置直播间标题与画布元素",
        ),
    }

    out_items = []
    passed_all = True
    for key, label, required, entry in CHECK_DEFS:
        ok, reason = results[key]
        out_items.append(
            {
                "key": key,
                "label": label,
                "required": required,
                "passed": ok,
                "reason": "" if ok else reason,
                "entry": entry,
            }
        )
        if required and not ok:
            passed_all = False

    return {
        "session_id": session.id,
        "strict_mode": strict_mode,
        "passed": passed_all,
        "items": out_items,
    }
