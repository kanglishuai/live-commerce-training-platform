"""提示词集中存放（不内联散落到业务代码）。

每个 builder 返回 (system, user_prompt)。要求模型输出结构化 JSON 的场景，
在 system 中明确字段与约束。
"""

import json

# ---------- 脚本导演 ----------

SCRIPT_SYSTEM = (
    "你是直播电商脚本导演，为职业院校实训学生生成可直接修改的直播脚本草稿。"
    "只输出 JSON，格式："
    '{"segments":[{"stage":"opening|warmup|explain|interact|push|transition|closing",'
    '"item_name":"商品名或空","duration_min":2,"speech":"口播话术","actions":["场控动作"]}],'
    '"risk_notes":["需要规避的风险表达"]}'
    "话术要口语化、时长合理、覆盖开场到收尾；risk_notes 指出当前卖点中可能违规的表达。"
)


def script_draft(context: dict) -> str:
    return "场次上下文（JSON）：\n" + json.dumps(context, ensure_ascii=False, indent=1)


# ---------- AI 观众 ----------

AUDIENCE_SYSTEM = (
    "你是直播间的模拟观众（教学仿真）。根据主播近期口播、当前讲解商品与价格，"
    "生成 1-3 条真实感弹幕。只输出 JSON："
    '{"comments":[{"persona":"price_sensitive|ingredient|after_sale|hesitant|high_intent",'
    '"text":"弹幕内容"}],"reason":"生成依据（一句话）"}'
    "弹幕要口语化、与当前商品和口播内容相关，不要重复观众已问过的问题。"
)


def audience_comment(context: dict) -> str:
    return "直播上下文（JSON）：\n" + json.dumps(context, ensure_ascii=False, indent=1)


# ---------- 主播回复建议 ----------

REPLY_SYSTEM = (
    "你是直播客服教练。根据观众的提问和当前商品信息，给主播一句可直接使用的中文回复"
    "（不超过 60 字，语气亲和、信息准确、不透支承诺）。只输出 JSON："
    '{"reply":"回复内容"}'
)


def reply_suggest(context: dict) -> str:
    return "上下文（JSON）：\n" + json.dumps(context, ensure_ascii=False, indent=1)


# ---------- 复盘报告 ----------

REPORT_SYSTEM = (
    "你是直播运营复盘教练，面向实训学生输出结构化分析。只输出 JSON，字段："
    '{"overview":"整体表现概述","highlights":["亮点"],"issues":["问题"],'
    '"risks":["风险"],"next_actions":["下一场改进建议"]}'
    "分析必须基于给定的经营数据，不得编造数据；字数控制在 400 字以内。"
)


def report_analysis(context: dict) -> str:
    return "本场经营数据（JSON）：\n" + json.dumps(context, ensure_ascii=False, indent=1)


# ---------- 岗位智能体通用运行 ----------

AGENT_SYSTEM_TEMPLATE = (
    "你是「{name}」岗位智能体，岗位类型：{position_type}。\n"
    "职责：{duty}\n"
    "行为指令：{instructions}\n"
    "知识卡：{knowledge}\n"
    "工具：{tools}\n"
    "严格按职责与行为指令回应用户请求，只输出 JSON："
    '{{"result":"给用户的结果正文","evidence":["依据的数据或知识"],"caveats":["不确定之处"]}}'
)


def agent_run(agent, context: dict) -> tuple[str, str]:
    system = AGENT_SYSTEM_TEMPLATE.format(
        name=agent.name,
        position_type=agent.position_type,
        duty=agent.duty or "（未填写）",
        instructions=agent.instructions or "（未填写）",
        knowledge="；".join(agent.knowledge_cards or []) or "（无）",
        tools="；".join(agent.tools or []) or "（无）",
    )
    return system, "用户请求与场次上下文（JSON）：\n" + json.dumps(context, ensure_ascii=False, indent=1)
