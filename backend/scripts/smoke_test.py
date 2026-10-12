"""端到端冒烟测试：覆盖 正常 / 模糊缺信息 / 异常越界 三类输入场景。

运行（在 backend/ 目录，先执行 python scripts/init_db.py）：
    python scripts/smoke_test.py

通过 TestClient 直连应用（不启动服务器），数据库来自 backend/.env。
全部断言通过时退出码为 0；任何失败退出码非 0（可用于 CI）。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
API = "/api/v1"

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    ok = bool(cond)
    results.append((name, ok, detail))
    print(("PASS  " if ok else "FAIL  ") + name + (f"  | {detail}" if detail else ""))
    return ok


def login(username: str, password: str) -> dict:
    r = client.post(f"{API}/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


def brief(r) -> str:
    text = r.text.replace("\n", " ")
    return f"[{r.status_code}] {text[:180]}"


def main() -> int:
    print("=" * 72)
    print("端到端冒烟测试：正常 / 模糊缺信息 / 异常越界")
    print("=" * 72)

    # ---------- 0. 健康检查与登录 ----------
    r = client.get("/health")
    check("健康检查：数据库连通", r.status_code == 200 and r.json()["database"] == "ok", brief(r))
    if r.json().get("database") != "ok":
        print("数据库不可用，请先执行 python scripts/init_db.py 并检查 backend/.env")
        return 1

    admin = login("admin", "Admin@123")
    teacher = login("teacher_li", "Teacher@123")
    stu1 = login("stu_001", "Student@123")
    stu2 = login("stu_002", "Student@123")
    stu3 = login("stu_003", "Student@123")

    # 异常越界：错误口令
    r = client.post(f"{API}/auth/login", json={"username": "stu_001", "password": "wrong-password"})
    check(
        "异常：错误口令被拒(401/INVALID_CREDENTIALS)",
        r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS",
        brief(r),
    )

    # ---------- 1. 教师建课与发任务 ----------
    classes = client.get(f"{API}/classes", headers=teacher).json()
    check("教师可见所带班级", len(classes) >= 1, f"{len(classes)} 个")
    class_id = classes[0]["id"]

    r = client.post(
        f"{API}/tasks",
        json={
            "title": f"助农直播综合实训（冒烟 {time.strftime('%H%M%S')}）",
            "description": "调研→选品→采购→定价→脚本→投流→装修→开播→履约→复盘",
            "class_id": class_id,
            "mode": "personal",
            "initial_fund_cents": 5_000_000,
            "market_heat": 7,
            "competition_level": 4,
            "strict_mode": False,
        },
        headers=teacher,
    )
    check("教师创建任务", r.status_code == 200, brief(r))
    task_id = r.json()["id"]
    r = client.post(f"{API}/tasks/{task_id}/publish", headers=teacher)
    check("发布任务", r.status_code == 200, brief(r))

    r = client.get(f"{API}/tasks", headers=stu1)
    check(
        "学生可见已发布任务",
        r.status_code == 200 and any(t["id"] == task_id for t in r.json()["items"]),
        f"共 {r.json()['total']} 个",
    )

    # ---------- 2. 学生开单：模糊缺信息场景 ----------
    r = client.post(f"{API}/tasks/{task_id}/sessions", json={}, headers=stu1)
    check("学生创建场次", r.status_code == 200, brief(r))
    sid = r.json()["id"]

    r = client.put(f"{API}/sessions/{sid}/research", json={"target_audience": "宝妈人群"}, headers=stu1)
    check(
        "模糊：调研缺必填字段被追问(422/VALIDATION_ERROR)",
        r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR",
        brief(r),
    )
    r = client.put(
        f"{API}/sessions/{sid}/research",
        json={
            "target_audience": "25-40 岁宝爸宝妈，关注产地与性价比",
            "reasons": "助农水果价格带 20-60 元、复购稳定，适合作为引流款",
            "competitors": "同价竞品多为普通快递，卖点同质化",
            "price_band": "20-60 元",
            "selling_points": ["产地直发", "现摘现发"],
        },
        headers=stu1,
    )
    check("完整调研保存成功", r.status_code == 200, brief(r))

    # ---------- 3. 选品 / 采购 / 定价 ----------
    products = client.get(f"{API}/products", params={"page_size": 50}, headers=stu1).json()["items"]
    check("商品库可检索", len(products) >= 6, f"{len(products)} 款")
    item_ids: list[int] = []
    for idx, product in enumerate(products[:3]):
        role = ["traffic", "profit", "image"][idx]
        r = client.post(
            f"{API}/sessions/{sid}/cart/items",
            json={"product_id": product["id"], "role": role},
            headers=stu1,
        )
        if r.status_code == 200:
            item_ids.append(r.json()["id"])
    check("货盘加入 3 款（引流/利润/形象）", len(item_ids) == 3, f"{len(item_ids)} 款")

    r = client.post(
        f"{API}/sessions/{sid}/purchases",
        json={"item_id": item_ids[0], "qty": 999_999, "supplier": "产地直供"},
        headers=stu1,
    )
    check(
        "异常：超预算采购被拒(INSUFFICIENT_FUNDS)",
        r.status_code == 400 and r.json()["code"] == "INSUFFICIENT_FUNDS",
        brief(r),
    )
    for iid in item_ids:
        r = client.post(
            f"{API}/sessions/{sid}/purchases",
            json={"item_id": iid, "qty": 50, "supplier": "产地直供"},
            headers=stu1,
        )
    check("正常采购成功（资金流水扣减）", r.status_code == 200, brief(r))
    for iid in item_ids:
        r = client.put(
            f"{API}/sessions/{sid}/cart/items/{iid}/pricing",
            json={"list_price_cents": 4990, "live_price_cents": 3990, "stock": 50},
            headers=stu1,
        )
    check("定价并上架", r.status_code == 200, brief(r))

    # ---------- 4. 策划 / 脚本 / 投流 / 装修 ----------
    client.put(
        f"{API}/sessions/{sid}/plan",
        json={
            "theme": "助农好物专场",
            "target_audience": "25-40 岁宝爸宝妈",
            "goals": {"gmv_cents": 3_000_00, "orders": 30},
            "main_items": item_ids[:2],
        },
        headers=stu1,
    )
    r = client.put(
        f"{API}/sessions/{sid}/script",
        json={
            "segments": [
                {"stage": "opening", "duration_min": 2, "speech": "欢迎来到助农好物专场！", "actions": ["公告"]},
                {"stage": "explain", "item_id": item_ids[0], "duration_min": 5, "speech": "这款沃柑产地直发，现摘现发。", "actions": ["切换商品"]},
                {"stage": "push", "duration_min": 3, "speech": "下方链接下单立减 10 元！", "actions": ["发送优惠券"]},
            ]
        },
        headers=stu1,
    )
    check("脚本保存", r.status_code == 200, brief(r))
    r = client.post(
        f"{API}/sessions/{sid}/ad-plans",
        json={
            "channel": "short_video",
            "objective": "enter_room",
            "budget_cents": 300_00,
            "audience": {"age": "25-40", "interest": "生鲜水果"},
            "creative": "产地实拍短视频",
            "bid_cents": 150,
        },
        headers=stu1,
    )
    check("创建投流计划", r.status_code == 200, brief(r))
    plan_id = r.json()["id"]
    r = client.post(f"{API}/ad-plans/{plan_id}/activate", headers=stu1)
    check("启用投流计划", r.status_code == 200, brief(r))
    r = client.put(
        f"{API}/sessions/{sid}/room",
        json={
            "title": "助农好物专场",
            "subtitle": "产地直发 · 现摘现发",
            "notice": "本场所有商品售后无忧",
            "welcome": "欢迎宝宝们，点点关注不迷路",
            "sensitive_words": ["最低价", "国家级", "绝对"],
            "quick_phrases": ["还有库存吗", "什么时候发货"],
            "faq": [{"q": "多久发货", "a": "48 小时内"}],
            "canvas": {"ratio": "9:16", "elements": [{"type": "title", "x": 40, "y": 60}]},
        },
        headers=stu1,
    )
    check("直播间装修保存", r.status_code == 200, brief(r))

    # ---------- 5. 开播检查 ----------
    r = client.get(f"{API}/sessions/{sid}/preflight", headers=stu1)
    pf = r.json()
    missing = [i["label"] for i in pf["items"] if i["required"] and not i["passed"]]
    check("开播检查通过", pf["passed"] is True, f"缺失：{missing}" if missing else "")

    # ---------- 6. 直播：开播 / tick / 事件 / 口播 / 中控 ----------
    r = client.post(f"{API}/sessions/{sid}/live/start", headers=stu1)
    check("开播", r.status_code == 200, brief(r))

    r = client.post(f"{API}/sessions/{sid}/live/tick", headers=stu1)
    check("首次 tick", r.status_code == 200, brief(r))
    time.sleep(1.05)
    for _ in range(5):
        r = client.post(f"{API}/sessions/{sid}/live/tick", headers=stu1)
        time.sleep(1.05)
    snapshot = r.json()["snapshot"] if r.status_code == 200 else {}
    check(
        "仿真推进 6 个周期并产生流量",
        r.status_code == 200 and snapshot.get("tick_count") == 6 and snapshot.get("viewers", 0) > 0,
        f"viewers={snapshot.get('viewers')}, online={snapshot.get('online')}, gmv={snapshot.get('gmv_cents')}",
    )

    r = client.get(f"{API}/sessions/{sid}/live/events", params={"since_id": 0, "type": "comment"}, headers=stu1)
    comments = r.json()["events"]
    check("AI 观众弹幕生成（仿真标识）", len(comments) > 0, f"{len(comments)} 条")
    if comments:
        check(
            "弹幕带 simulated 标识与 persona",
            all((e["payload"] or {}).get("simulated") for e in comments),
            f"personas={[e['payload'].get('persona') for e in comments[:3]]}",
        )
        r = client.post(
            f"{API}/sessions/{sid}/live/replies/suggest",
            json={"comment_event_id": comments[0]["id"]},
            headers=stu1,
        )
        check(
            "回复建议（来源字段标明 llm/rule）",
            r.status_code == 200 and r.json()["source"] in ("llm", "rule"),
            brief(r),
        )
        r = client.post(
            f"{API}/sessions/{sid}/live/replies",
            json={"comment_event_id": comments[0]["id"], "text": "亲，这款直播价叠加优惠券更划算，放心拍~"},
            headers=stu1,
        )
        check(
            "主播/客服回复评论（记入场次证据）",
            r.status_code == 200 and r.json()["type"] == "reply",
            brief(r),
        )

    r = client.post(
        f"{API}/sessions/{sid}/live/speech",
        json={"text": "这款是全网最低价，绝对不贵", "source": "manual"},
        headers=stu1,
    )
    check(
        "口播保存并命中敏感词→违规事件",
        r.status_code == 200 and r.json()["violation"] is True,
        brief(r),
    )
    r = client.post(
        f"{API}/sessions/{sid}/live/control",
        json={"action": "switch_item", "payload": {"item_id": item_ids[1]}},
        headers=stu1,
    )
    check("中控切换讲解商品", r.status_code == 200, brief(r))

    # 异常越界：直播中生成并提交复盘（履约未完成）
    r = client.post(f"{API}/sessions/{sid}/report/generate", headers=stu1)
    check("直播中可生成复盘草稿", r.status_code == 200, brief(r))
    r = client.post(f"{API}/sessions/{sid}/report/submit", headers=stu1)
    check(
        "异常：直播中/未履约不能提交复盘(FULFILLMENT_INCOMPLETE)",
        r.status_code == 400 and r.json()["code"] == "FULFILLMENT_INCOMPLETE",
        brief(r),
    )

    r = client.post(f"{API}/sessions/{sid}/live/stop", headers=stu1)
    check("下播", r.status_code == 200 and r.json()["status"] == "ended", brief(r))

    # 权限：学生之间互不可见
    r = client.get(f"{API}/sessions/{sid}", headers=stu2)
    check("权限：其他学生不可读该场次(403)", r.status_code == 403, brief(r))

    # ---------- 7. 履约与售后 ----------
    orders = client.get(
        f"{API}/sessions/{sid}/orders", params={"page_size": 200}, headers=stu1
    ).json()["items"]
    check("直播产生模拟订单", len(orders) > 0, f"{len(orders)} 单")
    for order in orders:
        client.post(f"{API}/orders/{order['id']}/ship", json={}, headers=stu1)
        client.post(f"{API}/orders/{order['id']}/logistics/advance", json={"node": "in_transit"}, headers=stu1)
        client.post(f"{API}/orders/{order['id']}/logistics/advance", json={"node": "delivering"}, headers=stu1)
        client.post(f"{API}/orders/{order['id']}/logistics/advance", json={"node": "signed"}, headers=stu1)
    r = client.get(f"{API}/orders/{orders[-1]['id']}", headers=stu1)
    check("订单推进至已签收", r.json()["order"]["status"] == "signed", brief(r))

    r = client.post(
        f"{API}/orders/{orders[-1]['id']}/logistics/advance",
        json={"node": "in_transit"},
        headers=stu1,
    )
    check(
        "异常：物流状态回退被拒(STATE_TRANSITION_INVALID)",
        r.status_code == 400 and r.json()["code"] == "STATE_TRANSITION_INVALID",
        brief(r),
    )

    r = client.post(
        f"{API}/sessions/{sid}/after-sales",
        json={"order_id": orders[-1]["id"], "type": "refund", "reason": "顾客反馈果径偏小"},
        headers=stu1,
    )
    check("创建售后工单", r.status_code == 200, brief(r))
    as_id = r.json()["id"]

    r = client.post(f"{API}/sessions/{sid}/report/generate", headers=stu1)
    check(
        "生成复盘报告（source 标明 llm/rule，规则兜底不伪装 AI）",
        r.status_code == 200 and r.json()["source"] in ("llm", "rule"),
        brief(r),
    )

    r = client.post(f"{API}/sessions/{sid}/report/submit", headers=stu1)
    check(
        "异常：售后未处理完不能提交复盘(FULFILLMENT_INCOMPLETE)",
        r.status_code == 400 and r.json()["code"] == "FULFILLMENT_INCOMPLETE",
        brief(r),
    )

    r = client.post(
        f"{API}/after-sales/{as_id}/resolve",
        json={"action": "approve", "note": "同意退款，商品退回库存"},
        headers=stu1,
    )
    check("售后处理完成（退款回补库存）", r.status_code == 200 and r.json()["status"] == "approved", brief(r))

    r = client.put(
        f"{API}/sessions/{sid}/report",
        json={"improvement_plan": "下一场加大短视频预热投放，引流款直播价再下探 5%，并准备 3 条差异化卖点话术。"},
        headers=stu1,
    )
    check("填写改进措施", r.status_code == 200, brief(r))
    r = client.post(f"{API}/sessions/{sid}/report/submit", headers=stu1)
    check("提交复盘并锁定", r.status_code == 200 and r.json()["locked"] is True, brief(r))
    r = client.put(f"{API}/sessions/{sid}/report", json={"improvement_plan": "再改改"}, headers=stu1)
    check(
        "异常：提交后修改被锁(REPORT_LOCKED)",
        r.status_code == 400 and r.json()["code"] == "REPORT_LOCKED",
        brief(r),
    )

    # ---------- 8. 教师评价 / 巡课 / 班级报告 ----------
    r = client.post(
        f"{API}/sessions/{sid}/score",
        json={"subjective_score": 88, "comment": "过程记录完整，转化率有提升空间"},
        headers=teacher,
    )
    check(
        "教师评分（客观分+主观分→综合分）",
        r.status_code == 200 and r.json()["comprehensive_score"] is not None,
        brief(r),
    )
    r = client.get(f"{API}/classes/{class_id}/report", headers=teacher)
    check("班级报告", r.status_code == 200 and r.json()["summary"]["sessions"] >= 1, brief(r))
    r = client.get(f"{API}/classes/{class_id}/patrol", headers=teacher)
    check("巡课工作台", r.status_code == 200 and len(r.json()["groups"]) >= 1, brief(r))

    # ---------- 9. 数据罗盘 ----------
    r = client.get(f"{API}/sessions/{sid}/metrics", params={"view": "overview"}, headers=stu1)
    ok = r.status_code == 200 and r.json()["data"]["orders"] >= 1 and len(r.json()["notes"]) >= 1
    check("数据罗盘·概况（含估算口径说明）", ok, brief(r))
    for view in ("sales", "traffic", "users"):
        r = client.get(f"{API}/sessions/{sid}/metrics", params={"view": view}, headers=stu1)
        check(f"数据罗盘·{view}", r.status_code == 200, brief(r))

    # ---------- 10. 竞赛排行榜 ----------
    r = client.post(
        f"{API}/competitions",
        json={"class_id": class_id, "name": f"同场对比赛 {time.strftime('%H%M%S')}", "metric": "comprehensive", "task_id": task_id},
        headers=teacher,
    )
    check("创建竞赛", r.status_code == 200, brief(r))
    comp_id = r.json()["id"]
    r = client.get(f"{API}/competitions/{comp_id}/leaderboard", headers=teacher)
    check("竞赛排行榜", r.status_code == 200 and len(r.json()["entries"]) >= 1, brief(r))

    # ---------- 11. 智能体全流程 ----------
    market = client.get(f"{API}/agents", params={"page_size": 50}, headers=stu3).json()["items"]
    builtin = [a for a in market if a["scope"] == "builtin"]
    check("智能体市场含内置模板", len(builtin) >= 3, f"{len(builtin)} 个")
    service_template = next((a for a in builtin if a["position_type"] == "service"), builtin[0])

    r = client.post(f"{API}/tasks/{task_id}/sessions", json={}, headers=stu3)
    sid2 = r.json()["id"]

    r = client.post(
        f"{API}/agents",
        json={
            "name": "我的客服助手",
            "position_type": "service",
            "duty": "处理观众咨询与售后争议",
            "instructions": "按 FAQ 与服务条款口径回复，不做超范围承诺",
            "tools": ["弹幕事件流", "FAQ 配置"],
            "knowledge_cards": ["七天无理由", "发货时效"],
            "from_template_id": service_template["id"],
        },
        headers=stu3,
    )
    check("创建个人智能体（含完成度）", r.status_code == 200, brief(r))
    agent_id = r.json()["id"]
    check("完成度计算", 0 < r.json()["completeness"] <= 1, f"completeness={r.json().get('completeness')}")

    r = client.post(
        f"{API}/agents/{agent_id}/rehearse",
        json={"prompt": "顾客说收到货有破损怎么办？", "context": {}},
        headers=stu3,
    )
    check("预演（不落库 persist=false）", r.status_code == 200 and r.json()["persist"] is False, brief(r))

    r = client.post(
        f"{API}/agents/{agent_id}/run",
        json={"prompt": "顾客说收到货有破损怎么办？", "context": {"session_id": sid2}},
        headers=stu3,
    )
    check(
        "正式运行（落库，source 标明 llm/rule 且含轨迹）",
        r.status_code == 200 and r.json()["source"] in ("llm", "rule") and len(r.json()["trace"]) >= 1,
        brief(r),
    )
    run_id = r.json()["id"]

    r = client.post(f"{API}/agent-runs/{run_id}/adopt", json={"target": "script"}, headers=stu3)
    check("采纳写入脚本（先生成后采纳）", r.status_code == 200, brief(r))
    r = client.post(f"{API}/agent-runs/{run_id}/adopt", json={"target": "script"}, headers=stu3)
    check("异常：重复采纳被拒", r.status_code == 409, brief(r))
    script = client.get(f"{API}/sessions/{sid2}/script", headers=stu3).json()
    check("脚本中出现采纳记录", len(script.get("adopted_notes") or []) == 1, str(script.get("adopted_notes"))[:120])

    r = client.post(f"{API}/agent-runs/{run_id}/rating", json={"score": 4, "comment": "模板可用，建议接入大模型"}, headers=stu3)
    check("运行结果评分", r.status_code == 200, brief(r))

    r = client.post(f"{API}/agents/{agent_id}/submit", headers=stu3)
    check("提交审核", r.status_code == 200 and r.json()["status"] == "pending", brief(r))
    r = client.post(f"{API}/agents/{agent_id}/review", json={"action": "approve", "note": "话术合规，可上架"}, headers=teacher)
    check("教师审核上架班级市场", r.status_code == 200 and r.json()["status"] == "published", brief(r))

    r = client.post(
        f"{API}/tasks/{task_id}/agent-assignments",
        json={"agent_id": agent_id, "instructions": "用它完成 3 个高频咨询的应答，提交运行记录"},
        headers=teacher,
    )
    check(
        "教师布置智能体作业",
        r.status_code == 200 and any(a.get("agent_id") == agent_id for a in r.json().get("agent_assignments") or []),
        brief(r),
    )
    r = client.get(f"{API}/tasks/{task_id}/agent-runs", headers=teacher)
    check("教师查看作业运行记录（含学生与轨迹）", r.status_code == 200 and r.json()["total"] >= 1, brief(r))

    # ---------- 12. 严格任务：开播检查阻断 ----------
    teacher_tasks = client.get(f"{API}/tasks", params={"page_size": 50}, headers=teacher).json()["items"]
    strict_task = next((t for t in teacher_tasks if t["strict_mode"]), None)
    if strict_task is not None:
        r = client.post(f"{API}/tasks/{strict_task['id']}/sessions", json={}, headers=stu1)
        sid3 = r.json()["id"]
        r = client.post(f"{API}/sessions/{sid3}/live/start", headers=stu1)
        check(
            "异常：严格任务未过开播检查不能开播(PREFLIGHT_FAILED)",
            r.status_code == 400 and r.json()["code"] == "PREFLIGHT_FAILED",
            brief(r),
        )
    else:
        check("严格任务检查用例", False, "未找到 strict_mode 任务（请先运行 init_db.py）")

    # ---------- 13. 停用账号令牌立即失效 ----------
    r = client.get(f"{API}/users", params={"keyword": "stu_010"}, headers=admin)
    target = next((u for u in r.json()["items"] if u["username"] == "stu_010"), None)
    if target:
        stu10 = login("stu_010", "Student@123")
        r = client.patch(f"{API}/users/{target['id']}", json={"status": "disabled"}, headers=admin)
        check("管理员停用账号", r.status_code == 200, brief(r))
        r = client.get(f"{API}/auth/me", headers=stu10)
        check(
            "停用后既有令牌立即失效(ACCOUNT_DISABLED)",
            r.status_code == 403 and r.json()["code"] == "ACCOUNT_DISABLED",
            brief(r),
        )
        client.patch(f"{API}/users/{target['id']}", json={"status": "active"}, headers=admin)  # 复原
    else:
        check("停用账号用例", False, "stu_010 不存在")

    # ---------- 汇总 ----------
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print("=" * 72)
    print(f"结果：{passed}/{total} 通过")
    failed = [name for name, ok, _ in results if not ok]
    if failed:
        print("失败用例：")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
