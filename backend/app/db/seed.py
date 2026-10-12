"""演示种子数据（幂等）：账号、班级、团队、商品库、任务、内置智能体。

账号口令仅用于本地教学演示，生产部署必须替换（见 README 已知限制）。
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.enums import AgentPosition, AgentScope, AgentStatus, Role, TaskMode, TaskStatus, TeamPosition
from app.core.security import hash_password
from app.models.agent import Agent
from app.models.commerce import Product
from app.models.task import Task
from app.models.user import Klass, Team, TeamMember, User

logger = logging.getLogger(__name__)

DEMO_PASSWORD_ADMIN = "Admin@123"
DEMO_PASSWORD_TEACHER = "Teacher@123"
DEMO_PASSWORD_STUDENT = "Student@123"


def _ensure_user(
    db: OrmSession, username: str, password: str, role: Role, real_name: str, class_id: int | None = None
) -> User:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        user = User(
            username=username,
            password_hash=hash_password(password),
            role=str(role),
            real_name=real_name,
            class_id=class_id,
        )
        db.add(user)
        db.flush()
    return user


PRODUCTS = [
    # (名称, 品牌, 类目, 成本, 市场价, 热度, 库存)
    ("沃柑 5 斤装 广西武鸣", "桂乡农", "助农水果", 1800, 3990, 8.5, 500),
    ("土蜂蜜 500g 深山原蜜", "山里蜜", "助农食品", 3500, 6900, 7.0, 300),
    ("五常大米 10 斤", "稻花香", "粮油", 4200, 6900, 6.5, 800),
    ("脐橙 10 斤装", "赣南果园", "助农水果", 3200, 5900, 8.0, 600),
    ("手工红薯粉条 2 斤", "老作坊", "助农食品", 1500, 2990, 5.5, 400),
    ("云南小粒咖啡豆 250g", "云咖", "饮品", 2800, 5900, 7.5, 350),
    ("山茶油 1L 冷榨", "大别山", "粮油", 6800, 12800, 6.0, 200),
    ("即食燕麦片 1kg", "轻食记", "轻食", 1200, 2990, 5.0, 700),
    ("红枣夹核桃 500g", "西域果园", "零食", 2200, 4590, 6.8, 450),
    ("农家散养土鸡蛋 30 枚", "田园记", "生鲜", 2600, 4990, 7.2, 300),
    ("冻干柠檬片 100g", "鲜果时光", "饮品", 900, 1990, 5.8, 800),
    ("非遗手工布鞋", "匠心坊", "非遗文创", 4500, 9900, 6.2, 150),
]

AGENT_TEMPLATES = [
    {
        "name": "选品洞察助手",
        "position_type": AgentPosition.SELECT,
        "duty": "基于类目热度、价格带与人群画像，给出选品与货盘结构建议。",
        "instructions": "输出引流款/利润款/形象款组合建议，并给出成本与毛利测算；所有建议必须标注数据来源（调研纪要/商品库）。",
        "tools": ["商品库检索", "市场调研数据"],
        "knowledge_cards": ["价格带判断", "毛利测算口径", "货盘结构三类定位"],
        "skills": ["数据分析", "选品策划"],
        "triggers": ["进入选品环节时推荐"],
    },
    {
        "name": "脚本导演",
        "position_type": AgentPosition.HOST,
        "duty": "生成直播脚本草稿，覆盖开场到收尾的完整节奏。",
        "instructions": "按开场/暖场/讲解/互动/逼单/转场/收尾组织脚本；话术口语化，单段 1-3 分钟；输出风险表达提示。",
        "tools": ["场次策划", "商品卖点"],
        "knowledge_cards": ["直播节奏设计", "合规话术边界"],
        "skills": ["脚本创作"],
        "triggers": ["进入脚本环节时推荐"],
    },
    {
        "name": "舆情回复助手",
        "position_type": AgentPosition.SERVICE,
        "duty": "针对观众提问与售后争议，给出合规、亲和的回复建议。",
        "instructions": "先确认问题类型，再按 FAQ 与服务条款口径回应；不做超范围承诺；争议升级教师复核。",
        "tools": ["弹幕事件流", "FAQ 配置"],
        "knowledge_cards": ["七天无理由", "发货时效", "成分表口径"],
        "skills": ["客户沟通"],
        "triggers": ["收到观众提问时推荐"],
    },
    {
        "name": "复盘教练",
        "position_type": AgentPosition.TEACHING,
        "duty": "基于场次经营数据生成结构化复盘要点与下一场改进建议。",
        "instructions": "从目标达成、货盘定价、流量投放、互动转化、合规履约五个维度诊断；结论必须引用具体指标值。",
        "tools": ["数据罗盘", "订单与售后记录"],
        "knowledge_cards": ["指标口径", "转化漏斗"],
        "skills": ["数据分析", "教学评价"],
        "triggers": ["下播后推荐"],
    },
]


def seed_demo_data(db: OrmSession) -> dict:
    """写入演示数据；若管理员账号已存在则整体跳过（幂等）。"""
    existing = db.execute(
        select(User.id).where(User.username == "admin")
    ).first()
    if existing:
        logger.info("演示数据已存在，跳过种子写入")
        return {"seeded": False, "reason": "admin 已存在"}

    admin = _ensure_user(db, "admin", DEMO_PASSWORD_ADMIN, Role.ADMIN, "平台管理员")
    teacher_li = _ensure_user(db, "teacher_li", DEMO_PASSWORD_TEACHER, Role.TEACHER, "李老师")
    teacher_wang = _ensure_user(db, "teacher_wang", DEMO_PASSWORD_TEACHER, Role.TEACHER, "王老师")

    klass_2301 = Klass(name="电商2301班", description="直播电商方向 · 实训班", teacher_id=teacher_li.id)
    klass_2302 = Klass(name="电商2302班", description="网络营销方向", teacher_id=teacher_wang.id)
    db.add_all([klass_2301, klass_2302])
    db.flush()

    students: list[User] = []
    for idx in range(1, 11):
        students.append(
            _ensure_user(
                db, f"stu_{idx:03d}", DEMO_PASSWORD_STUDENT, Role.STUDENT, f"学生{idx:02d}", klass_2301.id
            )
        )
    for idx in range(11, 14):
        _ensure_user(
            db, f"stu_{idx:03d}", DEMO_PASSWORD_STUDENT, Role.STUDENT, f"学生{idx:02d}", klass_2302.id
        )

    team1 = Team(class_id=klass_2301.id, name="第1小组（助农专场）", invite_code="TEAM0001", created_by=teacher_li.id)
    team2 = Team(class_id=klass_2301.id, name="第2小组（非遗文创）", invite_code="TEAM0002", created_by=teacher_li.id)
    db.add_all([team1, team2])
    db.flush()
    for member, position in zip(
        students[:3], [TeamPosition.HOST, TeamPosition.OPERATION, TeamPosition.CONTROL]
    ):
        db.add(TeamMember(team_id=team1.id, user_id=member.id, position=str(position)))
    for member, position in zip(students[3:6], [TeamPosition.HOST, TeamPosition.SERVICE, TeamPosition.AD]):
        db.add(TeamMember(team_id=team2.id, user_id=member.id, position=str(position)))

    for name, brand, category, cost, price, heat, stock in PRODUCTS:
        db.add(
            Product(
                name=name,
                brand=brand,
                category=category,
                cost_cents=cost,
                market_price_cents=price,
                heat=heat,
                stock=stock,
                selling_points=["产地直发", "品质保障", "售后无忧"],
                description=f"{name}，{brand} 出品，适合直播实训选品。",
                source="builtin",
                created_by=admin.id,
            )
        )

    task = Task(
        title="助农产品直播选品与运营实训",
        description="围绕助农水果与食品完成：调研 → 选品 → 采购 → 定价 → 脚本 → 投流 → 装修 → 开播 → 履约 → 复盘。",
        class_id=klass_2301.id,
        created_by=teacher_li.id,
        mode=str(TaskMode.PERSONAL),
        status=str(TaskStatus.PUBLISHED),
        initial_fund_cents=5_000_000,  # 5 万元
        market_heat=7.0,
        competition_level=4.0,
        strict_mode=False,
        weight_config={},  # 使用默认权重（见 services/scoring.py）
    )
    strict_task = Task(
        title="竞赛训练：同场对比带货赛",
        description="严格开播检查 + 相同初始条件，按综合分排名（竞赛模式）。",
        class_id=klass_2301.id,
        created_by=teacher_li.id,
        mode=str(TaskMode.TEAM),
        status=str(TaskStatus.PUBLISHED),
        initial_fund_cents=3_000_000,
        market_heat=8.0,
        competition_level=6.0,
        strict_mode=True,  # 未通过开播检查不允许开播
        weight_config={"objective_ratio": 0.7},
    )
    db.add_all([task, strict_task])

    for template in AGENT_TEMPLATES:
        agent = Agent(
            **template,
            scope=str(AgentScope.BUILTIN),
            owner_id=admin.id,
            status=str(AgentStatus.PUBLISHED),
            completeness=1.0,
        )
        db.add(agent)

    db.commit()
    logger.info("演示数据写入完成")
    return {
        "seeded": True,
        "accounts": {
            "admin": f"admin / {DEMO_PASSWORD_ADMIN}",
            "teacher": f"teacher_li / {DEMO_PASSWORD_TEACHER}",
            "student": f"stu_001 / {DEMO_PASSWORD_STUDENT}",
        },
        "class": klass_2301.name,
        "task": task.title,
    }
