# 直播运营虚拟仿真实训平台 · 接口文档（API v1）

> 适用版本：v0.1.0（骨架版）　　更新日期：2026-10-12
> 配套实现：`backend/`（FastAPI + SQLAlchemy + MySQL）
> 在线交互文档：启动后端后访问 `http://127.0.0.1:8000/docs`（Swagger UI）与 `/openapi.json`
> 一致性保障：`backend/scripts/verify_api_doc.py` 自动比对本文档与代码路由（CI/提交前执行）
> 说明：平台中的观众、订单、资金、物流均为**教学仿真数据**，不连接真实支付。

---

## 1. 概述

| 项目 | 说明 |
|---|---|
| Base URL | `http://{host}:8000/api/v1` |
| 数据格式 | `application/json; charset=utf-8`（文件上传为 `multipart/form-data`） |
| 认证方式 | HTTP Bearer（JWT，HS256），登录接口下发，默认有效期 720 分钟 |
| 角色 | `admin` 管理员 / `teacher` 教师 / `student` 学生 |
| 金额单位 | **分（int）**，字段名统一以 `_cents` 结尾（避免浮点误差） |
| 时间格式 | 请求/响应统一 **UTC ISO8601**（响应带 `Z`，如 `2026-10-12T07:28:02Z`） |
| 分页 | 请求 `?page=1&page_size=20`；响应 `{items, total, page, page_size}` |

请求头示例：

```
Authorization: Bearer <token>
Content-Type: application/json
```

---

## 2. 通用约定

### 2.1 认证与账号状态

- 除 `/auth/login`、`/health` 外，所有接口必须携带有效令牌，否则 `401 AUTH_REQUIRED`。
- **账号停用即时生效**：管理员将账号置为 `disabled` 后，该用户既有令牌立即失效（`403 ACCOUNT_DISABLED`）。

### 2.2 错误响应（统一结构）

```json
{
  "code": "INSUFFICIENT_FUNDS",
  "message": "经营资金不足：本次需要 17999982.00 元，当前余额 50000.00 元",
  "context": {"required_cents": 1799998200, "balance_cents": 5000000}
}
```

- 参数校验失败返回 `422 VALIDATION_ERROR`，`context.details` 逐字段说明缺什么（模糊输入必须显式报错，不静默放行）。
- 错误码全集见 [附录 B](#附录-b错误码)。

### 2.3 金额、库存与资金一致性

- 资金变动一律写入 `fund_txns` 流水（采购 / 投流 / 销售回款 / 退款），**任何余额变化可审计**。
- 余额不足时显式返回 `INSUFFICIENT_FUNDS`；退款类型售后单允许余额为负（应退必退）。
- 库存流转：采购 `+qty` → 成交 `-qty`（售罄自动下架）→ 拒收/退款回补 `+qty`。
- 金额相关写操作在 MySQL 中使用 `SELECT ... FOR UPDATE` 行锁。

### 2.4 经营数据修改窗口

- 场次处于 `live` / `paused` 时，**不允许**修改货盘/采购/定价/促销/投流等经营准备数据（直播中上下架走中控动作 `switch_item`）。
- 复盘**提交后锁定**，所有相关业务记录只读（`400 REPORT_LOCKED`）；教师可退回（`report/return`）后重新修改提交。

### 2.5 幂等与去重

- 账号、货盘商品（同一场次同一商品）、团队成员（同一团队同一成员）均做唯一性校验，重复创建返回 `409 DUPLICATE`。
- `live/tick` 有最小间隔限制（默认 1 秒，`SIM_TICK_MIN_INTERVAL_SECONDS`），过密调用返回 `429 TICK_TOO_FREQUENT`。

---

## 3. 权限模型（三级角色 + 资源级）

| 角色 | 数据范围 |
|---|---|
| `admin` | 全局；账号与角色管理、商品库维护、协助教学组织 |
| `teacher` | 自己创建的班级/任务/团队；所带班级学生的场次、报告、成绩；巡课与评分 |
| `student` | 本人场次（团队场次含同队成员）；本班已发布任务；本班班级共享智能体 |

资源级规则（关键约束，均有自动化用例覆盖）：

1. 学生之间**不可互读**场次记录（`403 PERMISSION_DENIED`）。
2. 写入类接口（调研/采购/开播/履约等）**仅场次归属人（含同队成员）**可调用；教师只读旁路用于巡课/评分/退回复盘。
3. 口播与行为证据按场次归属限制读写，防止他人代写训练证据。
4. 智能体「先生成、后采纳」：只有运行者本人 `adopt` 才能将结果写入其有权修改的脚本/复盘。

---

## 4. 状态机

### 4.1 场次 `sessions.status`

```
preparing ──开播──▶ live ◀──恢复── paused
                      │              │
                      └──下播────────┴──▶ ended ──提交复盘──▶ submitted
                                                              │
                                             教师退回 ◀────────┘（回到 ended）
```

| 值 | 中文 | 可用操作 |
|---|---|---|
| `preparing` | 准备中 | 经营准备、开播检查、开播 |
| `live` | 直播中 | tick、口播、行为采样、中控、回复 |
| `paused` | 已暂停 | 恢复直播、下播（tick 不推进） |
| `ended` | 已下播 | 履约、售后、生成复盘、提交复盘 |
| `submitted` | 已提交 | 只读（教师可退回） |

### 4.2 订单 `orders.status` 与物流 `logistics_node`

```
订单：pending_ship ──发货──▶ shipping ──签收──▶ signed ──▶ closed
                 └──────────────关闭──────────────┘
物流：picked_up ──▶ in_transit ──▶ delivering ──▶ signed
                      └──────── rejected（拒收：订单转 closed，库存回补）────────┘
```

| 订单状态 | 中文 | | 物流节点 | 中文 |
|---|---|---|---|---|
| `pending_ship` | 待发货 | | `picked_up` | 揽收 |
| `shipping` | 运输中 | | `in_transit` | 运输中 |
| `signed` | 已签收 | | `delivering` | 派送中 |
| `closed` | 已关闭 | | `signed` | 签收 |
| | | | `rejected` | 拒收 |

- 非法迁移（如已签收回退运输中）返回 `400 STATE_TRANSITION_INVALID`，`context.allowed` 给出合法目标。
- **未完成履约或售后的场次不能提交复盘**（`400 FULFILLMENT_INCOMPLETE`）。

### 4.3 售后工单 `after_sales.status`

```
pending ──同意──▶ approved ──结案──▶ closed
   └────驳回──▶ rejected ──结案──▶ closed
```

同意退款/退货类工单：写退款流水（允许余额为负）→ 库存回补 → 订单关闭。

---

## 5. 接口清单

> 路径均省略 Base URL 前缀 `/api/v1`。权限列 `——` 表示登录即可（受资源级规则约束）。

### 5.1 认证

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/auth/login` | 公开 | 登录，返回令牌与用户信息 |
| GET | `/auth/me` | 登录 | 当前登录用户 |
| POST | `/auth/change-password` | 登录 | 修改本人登录口令 |

**POST `/auth/login`**

```json
// 请求
{ "username": "stu_001", "password": "Student@123" }
// 响应
{
  "token": "eyJhbGciOi...",
  "token_type": "Bearer",
  "expires_in": 43200,
  "user": { "id": 4, "username": "stu_001", "role": "student", "real_name": "学生01",
            "class_id": 1, "status": "active", "created_at": "2026-10-12T07:26:52Z" }
}
```

### 5.2 用户管理

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/users` | 管理员 | 创建账号（role/real_name/class_id） |
| GET | `/users` | 教师/管理员 | 账号列表（教师仅见所带班级学生与本人；支持 role/class_id/keyword 过滤） |
| GET | `/users/{user_id}` | 登录 | 账号详情（学生仅本人；教师仅所带学生） |
| PATCH | `/users/{user_id}` | 管理员 | 修改姓名/班级/**停用**/角色（停用即时生效） |
| POST | `/users/import` | 教师/管理员 | 批量导入学生，返回 `{created, skipped[{username, reason}]}` |

**POST `/users/import`**

```json
{
  "class_id": 1,
  "students": [
    { "username": "stu_101", "real_name": "张三", "password": "Student@123" },
    { "username": "stu_002", "real_name": "重复账号" }
  ]
}
// 响应：skipped 说明未创建原因（账号已存在 / 批次内重复 / 仅学生账号可加入班级）
```

### 5.3 班级与团队

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/classes` | 教师/管理员 | 创建班级（创建者即班主任） |
| GET | `/classes` | 登录 | 班级列表（按角色范围） |
| GET | `/classes/{class_id}` | —— | 班级详情（含学生数/团队数） |
| PATCH | `/classes/{class_id}` | 管理员/班主任 | 修改班级 |
| POST | `/classes/{class_id}/students` | 教师/管理员 | 将指定用户加入班级 |
| GET | `/classes/{class_id}/students` | —— | 班级学生列表（分页） |
| POST | `/classes/{class_id}/teams` | —— | 创建团队（学生创建时自动加入并默认岗位 host） |
| GET | `/classes/{class_id}/teams` | —— | 团队列表（含成员与岗位） |
| GET | `/teams/{team_id}` | —— | 团队详情 |
| PATCH | `/teams/{team_id}` | 教师/创建者 | 修改团队 |
| DELETE | `/teams/{team_id}` | 教师/创建者 | 解散团队（已关联场次时拒绝） |
| POST | `/teams/{team_id}/members` | —— | 添加成员并配置岗位 |
| DELETE | `/teams/{team_id}/members/{user_id}` | 教师/创建者 | 移除成员 |

**POST `/teams/{team_id}/members`**

```json
{ "user_id": 6, "position": "control" }
// position 枚举：host 主播 / operation 直播运营 / control 场控 / service 客服 / select 选品 / ad 投手
```

### 5.4 任务

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/tasks` | 教师/管理员 | 创建任务（草稿态） |
| GET | `/tasks` | 登录 | 任务列表（教师：本人创建；学生：本班已发布） |
| GET | `/tasks/{task_id}` | —— | 任务详情 |
| PATCH | `/tasks/{task_id}` | 教师/管理员 | 修改任务（已关闭不可改） |
| POST | `/tasks/{task_id}/publish` | 教师/管理员 | 发布任务（学生端出现作业入口） |
| POST | `/tasks/{task_id}/close` | 教师/管理员 | 关闭任务 |
| GET | `/tasks/{task_id}/checklist` | —— | 开播前阶段清单（需传 `session_id` 查询参数） |
| POST | `/tasks/{task_id}/agent-assignments` | 教师/管理员 | 布置智能体作业 `{agent_id, instructions}` |
| GET | `/tasks/{task_id}/agent-runs` | 教师/管理员 | 任务下全部智能体运行记录（含学生姓名） |

**POST `/tasks`（题设 5.3 任务配置项全覆盖）**

```json
{
  "title": "助农产品直播选品与运营实训",
  "description": "调研→选品→采购→定价→脚本→投流→装修→开播→履约→复盘",
  "class_id": 1,
  "mode": "personal",              // personal 个人练习 / team 团队协作
  "initial_fund_cents": 5000000,   // 初始经营资金（分）= 5 万元
  "market_heat": 7.0,              // 市场热度 1-10，影响仿真进房量
  "competition_level": 4.0,        // 竞争难度 1-10，折减自然流量
  "strict_mode": false,            // true：未通过开播检查不允许开播
  "weight_config": {               // 可选：评分权重（缺省用系统默认）
    "dimensions": { "operation": 30, "process": 25, "service": 20, "compliance": 15, "review": 10 },
    "objective_ratio": 0.6         // 综合成绩中客观分占比
  },
  "start_at": null, "end_at": null
}
```

### 5.5 场次与经营准备

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/tasks/{task_id}/sessions` | —— | 创建场次（学生；`team_id` 可选） |
| GET | `/sessions` | 登录 | 场次列表（教师看所带班级；支持 task_id/status 过滤） |
| GET | `/sessions/{session_id}` | —— | 场次详情（含研究/策划/脚本/装修/实时快照） |
| GET | `/sessions/{session_id}/task` | —— | 场次关联任务 |
| PUT | `/sessions/{session_id}/research` | 归属人 | 保存调研纪要 |
| PUT | `/sessions/{session_id}/plan` | 归属人 | 保存直播策划 |
| GET/PUT | `/sessions/{session_id}/script` | 读：——；写：归属人 | 直播脚本（分段） |
| GET/PUT | `/sessions/{session_id}/room` | 读：——；写：归属人 | 直播间装修配置 |
| POST | `/sessions/{session_id}/room/copy` | 归属人 | 复制他场装修到本场（历史装修只读，不被覆盖） |
| GET | `/sessions/{session_id}/preflight` | —— | 开播检查（必须项/建议项 + 缺失原因 + 返回入口） |

**PUT `/sessions/{id}/research`** —— 模糊输入场景：`target_audience`、`reasons` 必填，缺字段返回 422：

```json
{
  "target_audience": "25-40 岁宝爸宝妈，关注产地与性价比",
  "reasons": "助农水果价格带 20-60 元、复购稳定，适合作为引流款",
  "competitors": "同价竞品多为普通快递，卖点同质化",
  "price_band": "20-60 元",
  "selling_points": ["产地直发", "现摘现发"],
  "recommended_slot": "20:00-22:00"
}
```

**PUT `/sessions/{id}/script`**

```json
{
  "segments": [
    { "stage": "opening",  "duration_min": 2, "speech": "欢迎来到助农好物专场！", "actions": ["公告"] },
    { "stage": "explain",  "item_id": 4, "duration_min": 5, "speech": "这款沃柑产地直发，现摘现发。", "actions": ["切换商品"] },
    { "stage": "push",     "duration_min": 3, "speech": "下方链接下单立减 10 元！", "actions": ["发送优惠券"] }
  ]
}
// stage 枚举：opening 开场 / warmup 暖场 / explain 讲解 / interact 互动 / push 逼单 / transition 转场 / closing 收尾
// 响应额外包含 adopted_notes（智能体「采纳」写入的记录）
```

**PUT `/sessions/{id}/room`**

```json
{
  "background": "自然助农", "title": "助农好物专场", "subtitle": "产地直发 · 现摘现发",
  "notice": "本场所有商品售后无忧", "welcome": "欢迎宝宝们，点点关注不迷路",
  "sensitive_words": ["最低价", "国家级", "绝对"],
  "quick_phrases": ["还有库存吗", "什么时候发货"],
  "faq": [{ "q": "多久发货", "a": "48 小时内" }],
  "cover_url": "", "intro": "", "planned_start_at": null,
  "canvas": { "ratio": "9:16", "elements": [{ "type": "title", "x": 40, "y": 60 }] }
}
```

**GET `/sessions/{id}/preflight`**

```json
{
  "session_id": 2, "strict_mode": false, "passed": true,
  "items": [
    { "key": "research", "label": "调研纪要", "required": true,  "passed": true,  "reason": "", "entry": "research" },
    { "key": "cart",     "label": "货盘商品", "required": true,  "passed": true,  "reason": "", "entry": "cart" },
    { "key": "role_structure", "label": "货盘定位结构（引流款 + 利润款）", "required": true, "passed": true, "reason": "", "entry": "cart" },
    { "key": "purchase", "label": "商品采购", "required": true,  "passed": true,  "reason": "", "entry": "purchase" },
    { "key": "pricing",  "label": "定价设置", "required": true,  "passed": true,  "reason": "", "entry": "pricing" },
    { "key": "plan",     "label": "直播策划", "required": false, "passed": true,  "reason": "", "entry": "plan" },
    { "key": "script",   "label": "直播脚本", "required": true,  "passed": true,  "reason": "", "entry": "script" },
    { "key": "ad",       "label": "流量推广计划", "required": false, "passed": true, "reason": "", "entry": "ad" },
    { "key": "room",     "label": "直播间装修", "required": true, "passed": true, "reason": "", "entry": "room" }
  ]
}
// strict_mode=true 且未通过时，开播返回 400 PREFLIGHT_FAILED（context.missing 列出缺失项）
```

### 5.6 商品库

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/products` | 登录 | 检索（keyword/category/status/sort=heat\|price_asc\|price_desc） |
| GET | `/products/{product_id}` | 登录 | 商品详情 |
| POST | `/products` | 教师/管理员 | 新增商品（成本/市场价/热度/库存/图文/卖点） |
| PATCH | `/products/{product_id}` | 教师/管理员 | 维护商品 |

### 5.7 货盘、采购、资金、促销、投流

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/sessions/{id}/cart` | —— | 货盘视图（含成本、余额、采购成本合计） |
| POST | `/sessions/{id}/cart/items` | 归属人 | 加入货盘 `{product_id, role}` |
| POST | `/sessions/{id}/cart/custom-items` | 归属人 | 添加自定义商品 |
| PATCH | `/sessions/{id}/cart/items/{item_id}` | 归属人 | 维护图文/卖点/定位/排序/上下架 |
| DELETE | `/sessions/{id}/cart/items/{item_id}` | 归属人 | 移出货盘（已有采购记录时拒绝） |
| PUT | `/sessions/{id}/cart/items/{item_id}/pricing` | 归属人 | 设置划线价/直播价/库存（库存>0 自动上架） |
| POST | `/sessions/{id}/purchases` | 归属人 | 采购下单（校验资金，写流水，库存入账） |
| GET | `/sessions/{id}/purchases` | —— | 采购记录 |
| GET | `/sessions/{id}/fund-txns` | —— | 资金流水 |
| POST | `/sessions/{id}/promotions` | 归属人 | 配置促销（优惠券/满减/秒杀/赠品/拼团/抽奖） |
| GET | `/sessions/{id}/promotions` | —— | 促销列表 |
| PATCH | `/promotions/{promotion_id}` | 归属人 | 启停促销 |
| DELETE | `/promotions/{promotion_id}` | 归属人 | 删除促销 |
| POST | `/sessions/{id}/ad-plans` | 归属人 | 创建投流计划 |
| GET | `/sessions/{id}/ad-plans` | —— | 投流计划列表 |
| POST | `/ad-plans/{plan_id}/activate` | 归属人 | 启用（直播 tick 中按周期消耗预算） |
| POST | `/ad-plans/{plan_id}/stop` | 归属人 | 停止 |
| DELETE | `/ad-plans/{plan_id}` | 归属人 | 删除（已有消耗时拒绝） |

**PUT `/sessions/{id}/cart/items/{item_id}/pricing`**

```json
{ "list_price_cents": 4990, "live_price_cents": 3990, "stock": 50 }
// 约束：直播价不应高于划线价（422）；库存 > 0 且状态为 editing 时自动上架
```

**POST `/sessions/{id}/purchases`** —— 资金不足场景返回 `400 INSUFFICIENT_FUNDS`：

```json
// 请求（unit_cost_cents 不传则取商品成本）
{ "item_id": 4, "qty": 50, "supplier": "产地直供" }
// 响应
{
  "purchase": { "id": 8, "session_id": 2, "item_id": 4, "supplier": "产地直供",
                "qty": 50, "unit_cost_cents": 1800, "total_cents": 90000,
                "created_at": "2026-10-12T07:27:56Z" },
  "fund_balance_cents": 4525000
}
```

**POST `/sessions/{id}/ad-plans`**

```json
{
  "channel": "short_video",        // short_video 短视频预热 / feed 信息流 / reservation 直播预约 / social 社交渠道
  "objective": "enter_room",       // exposure 曝光 / click 点击 / enter_room 进房 / order 成交
  "budget_cents": 30000,           // 总预算（分）
  "audience": { "age": "25-40", "interest": "生鲜水果" },
  "creative": "产地实拍短视频",
  "bid_cents": 150
}
// 投流换算（教学口径）：每 1 元花费约带来 1 名进房，按优化目标修正（exposure 0.3 / click 0.6 / enter_room 1.0 / order 1.2）
```

### 5.8 直播（实时仿真）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/sessions/{id}/live/start` | 归属人 | 开播（严格任务校验开播检查） |
| POST | `/sessions/{id}/live/pause` | 归属人 | 暂停（tick 不推进） |
| POST | `/sessions/{id}/live/resume` | 归属人 | 恢复 |
| POST | `/sessions/{id}/live/stop` | 归属人 | 下播（进入履约与复盘） |
| POST | `/sessions/{id}/live/tick` | 归属人 | **推进一个仿真周期**（前端定频调用） |
| GET | `/sessions/{id}/live/state` | —— | 当前状态与快照（不推进） |
| GET | `/sessions/{id}/live/events` | —— | 事件增量拉取（`since_id` 游标） |
| POST | `/sessions/{id}/live/speech` | 归属人 | 提交口播识别文本（含敏感词违规检测） |
| POST | `/sessions/{id}/live/behavior` | 归属人 | 提交出镜行为采样（终端侧，帧不上传） |
| POST | `/sessions/{id}/live/control` | 归属人 | 中控动作（切换商品/优惠券/秒杀/抽奖/公告/投票/置顶/福利） |
| POST | `/sessions/{id}/live/replies` | 归属人 | 主播回复评论 |
| POST | `/sessions/{id}/live/replies/suggest` | —— | AI 回复建议（不落库，`source=llm\|rule`） |
| POST | `/speech/transcribe` | 登录 | 音频转写（可选外部 ASR；未配置返回 `501 ASR_NOT_CONFIGURED`） |

**实时方案（重要）**

前端以固定周期（建议 2-3 秒）调用 `live/tick`，服务端按 `(场次, 周期号)` 为随机种子推进仿真，保证：
同一场次重放可复现、无后台任务/消息队列依赖、可暂停可控。事件采用 `since_id` 增量拉取，
后续如需 WebSocket 推送，可保持同一事件契约平滑替换。

**POST `/sessions/{id}/live/tick`** 响应：

```json
{
  "session_id": 2, "status": "live",
  "snapshot": { "online": 281, "viewers": 382, "peak_online": 281, "likes": 318, "comments": 7,
                "item_clicks": 149, "orders": 8, "gmv_cents": 39900, "tick_count": 6,
                "current_item_id": 5, "updated_at": "2026-10-12T07:28:02.123456" },
  "new_events": [ { "id": 30, "type": "order", "payload": { "order_no": "SO2-D60AE1C79D", "amount_cents": 3990 } } ],
  "latest_event_id": 33
}
```

仿真影响因子（可在 `services/simulation.py · SIM_PARAMS` 调整）：市场热度、竞争难度、投流计划（预算/出价/优化目标）、
货盘结构（引流款加权）、直播价与划线价差、促销生效、库存、口播与互动动作、AI 观众高意向。

**GET `/sessions/{id}/live/events?since_id=0&type=comment&limit=200`** 响应：

```json
{
  "events": [
    { "id": 12, "session_id": 2, "type": "comment", "ts": "2026-10-12T07:28:00Z",
      "payload": { "text": "沃柑这个价还能再低吗？", "persona": "price_sensitive", "simulated": true },
      "source": "rule" }
  ],
  "latest_event_id": 33
}
// type 枚举：metric 指标快照 / speech 口播 / behavior 行为采样 / comment 弹幕 /
//            reply 主播回复 / control 中控动作 / order 订单 / violation 违规 / ai_decision AI 决策 / system 系统
```

**POST `/sessions/{id}/live/speech`**

```json
// 请求
{ "text": "这款是全网最低价，绝对不贵", "source": "manual" }
// source：server_asr 服务端识别 / browser_asr 浏览器识别 / manual 手动补录
// 响应
{ "event": { "id": 30, "type": "speech", "payload": { "text": "...", "chars": 13 } },
  "violation": true,
  "messages": ["口播已保存（来源：manual）", "命中敏感词：最低价、绝对，已记录违规"] }
```

**POST `/sessions/{id}/live/control`**

```json
{ "action": "switch_item", "payload": { "item_id": 5 } }
// action：switch_item 切换讲解商品（须已在货盘上架）/ push_coupon 推送优惠券 / seckill 秒杀 /
//         lottery 抽奖 / announcement 公告（payload.text 必填）/ poll 投票 /
//         pin_comment 置顶评论 / fan_benefit 粉丝福利
```

### 5.9 订单、物流与售后

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/sessions/{id}/orders` | —— | 订单列表（status 过滤 + 分页） |
| GET | `/orders/{order_id}` | —— | 订单详情（含售后单） |
| POST | `/orders/{order_id}/ship` | 归属人 | 发货：`pending_ship → shipping`，物流节点 `picked_up` |
| POST | `/orders/{order_id}/logistics/advance` | 归属人 | 推进物流节点（严格顺序）；`signed` 同步订单签收；`rejected` 关闭订单并回补库存 |
| POST | `/orders/{order_id}/close` | 归属人 | 关闭订单 |
| GET | `/sessions/{id}/after-sales` | —— | 售后工单列表（status 过滤） |
| POST | `/sessions/{id}/after-sales` | 归属人 | 创建工单 `{order_id, type, reason, amount_cents?}` |
| GET | `/after-sales/{id}` | —— | 工单详情 |
| POST | `/after-sales/{id}/resolve` | 归属人 | 同意/驳回 `{action: "approve"\|"reject", note}` |
| POST | `/after-sales/{id}/close` | 归属人 | 结案 |

**POST `/orders/{order_id}/logistics/advance`**

```json
// 请求
{ "node": "in_transit", "note": "" }
// node：picked_up 揽收 / in_transit 运输中 / delivering 派送中 / signed 签收 / rejected 拒收
// 非法迁移示例响应
{ "code": "STATE_TRANSITION_INVALID",
  "message": "物流不允许从 signed 迁移到 in_transit",
  "context": { "current": "signed", "target": "in_transit", "allowed": [] } }
```

**POST `/sessions/{id}/after-sales`**

```json
// 请求（amount_cents 不传时：退款/退货/超卖/延迟发货默认订单全额）
{ "order_id": 1, "type": "refund", "reason": "顾客反馈果径偏小" }
// type：refund 退款 / return 退货 / exchange 换货 / complaint 投诉 / oversell 超卖 / delay 延迟发货
```

### 5.10 复盘与评价

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/sessions/{id}/metrics` | —— | 数据罗盘（查询参数 `view`=overview/sales/traffic/users，含数据来源与估算口径 `notes`） |
| POST | `/sessions/{id}/report/generate` | 归属人 | 生成/重新生成复盘报告（`source=llm\|rule`） |
| GET | `/sessions/{id}/report` | —— | 读取报告 |
| PUT | `/sessions/{id}/report` | 归属人 | 填写改进措施（草稿，锁定后 400 REPORT_LOCKED） |
| POST | `/sessions/{id}/report/submit` | 归属人 | 提交复盘（校验履约售后完成 → 锁定） |
| POST | `/sessions/{id}/report/return` | 教师 | 退回复盘（回到可编辑） |
| POST | `/sessions/{id}/score` | 教师 | 评分 `{subjective_score, comment}` → 综合成绩 |
| GET | `/sessions/{id}/score` | —— | 读取成绩（未评分 404） |
| GET | `/classes/{class_id}/report` | —— | 班级报告（进度/场次/成绩汇总） |
| GET | `/classes/{class_id}/patrol` | —— | 巡课工作台（状态/指标/最新弹幕） |

**GET `/sessions/{id}/metrics?view=overview`**

```json
{
  "session_id": 2, "view": "overview",
  "data": { "viewers": 382, "peak_online": 281, "online": 281, "item_clicks": 149, "click_rate": 0.3901,
            "orders": 8, "conversion_rate": 0.0537, "gmv_cents": 39900, "aov_cents": 4988,
            "interaction_rate": 0.8508, "new_fans_estimate": 19, "refund_orders": 1, "refund_rate": 0.125,
            "ship_settled": 8, "tick_count": 6, "violations": 1 },
  "notes": ["观众、订单、资金、物流均为教学仿真数据，不连接真实支付。",
            "广告进房人数按“每 1 元约 1 人”的换算口径估算，仅用于教学分析。",
            "新增粉丝、渠道占比为估算值，样本不足时不输出趋势（需 ≥3 个采样点）。"]
}
// sales 视图：trend（tick 序列）/ item_contribution / funnel；样本 < 3 时 trend 为空且 trend_sufficient=false
// traffic 视图：channels / ad_spend / roas / 自然与投流进房估算
// users 视图：AI 观众人群构成与成交分布（仿真设定，非真实用户）
```

**POST `/sessions/{id}/report/generate`** 响应（未配置大模型时 `source=rule`，明确标识规则兜底）：

```json
{
  "id": 1, "session_id": 2, "source": "rule",
  "content": {
    "sections": [
      { "key": "goal", "title": "目标达成", "summary": "任务目标 GMV 3,000.00 元，实际 399.00 元",
        "bullets": ["访客 382 人，峰值在线 281 人", "成交 8 单，客单价 49.88 元"] }
    ],
    "overview": "本场为「助农直播综合实践」的直播训练，累计观看 382 人，产生 8 笔模拟订单。",
    "highlights": ["本场达成成交 8 单，GMV 399.00 元"],
    "issues": ["GMV 目标 3,000.00 元 未达成（实际 399.00 元）"],
    "risks": ["出现 1 次敏感词违规，需规范直播话术"],
    "next_actions": ["增加限时优惠与逼单话术，缩短决策链路"],
    "data_source": "系统过程数据汇总（规则生成）"
  },
  "improvement_plan": "", "status": "draft", "locked": false, "returned_reason": ""
}
```

**POST `/sessions/{id}/score`** 响应（客观分 5 维度加权 + 主观分 → 综合成绩）：

```json
{
  "id": 1, "session_id": 2, "objective_score": 81.9,
  "objective_detail": {
    "dimensions": { "operation": 49.8, "process": 100.0, "service": 100.0, "compliance": 80, "review": 100.0 },
    "weights": { "operation": 30, "process": 25, "service": 20, "compliance": 15, "review": 10 },
    "objective_ratio": 0.6,
    "evidence": { "profit_cents": -17211, "checklist_passed": "9/9", "orders_settled": "8/8",
                  "after_sales_resolved": "1/1", "violations": 1, "report_status": "scored" }
  },
  "subjective_score": 88, "comprehensive_score": 84.3,
  "weights": { "operation": 30, "process": 25, "service": 20, "compliance": 15, "review": 10 },
  "teacher_id": 2, "scored_at": "2026-10-12T07:28:03Z"
}
```

客观分维度口径：经营结果（期末资金+库存残值相对初始资金）、过程完成度（准备清单通过率）、
服务（履约完成率 70% + 售后处理率 30%，无订单时中性 70 分）、合规（100-20×违规次数，≥3 次记 0）、
复盘质量（报告存在 40 + 改进措施≥30 字 30 + 已提交 30）。

### 5.11 竞赛

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/competitions` | 教师/管理员 | 创建竞赛 `{class_id, name, metric, task_id?, rules?}` |
| GET | `/competitions` | 登录 | 竞赛列表（按角色范围） |
| GET | `/competitions/{id}/leaderboard` | —— | 排行榜（含各口径原始值） |
| POST | `/competitions/{id}/close` | 教师/管理员 | 结束竞赛 |

metric 口径：`gmv` / `profit`（利润 = 期末资金 − 初始资金）/ `conversion` / `compliance` / `interaction` / `fulfillment` / `comprehensive`（默认，取客观综合分）。

**GET `/competitions/{id}/leaderboard`**

```json
{
  "competition_id": 1, "metric": "comprehensive",
  "entries": [
    { "rank": 1, "session_id": 2, "owner_id": 4, "owner_name": "学生01",
      "session_name": "学生01 第1场", "session_status": "submitted", "value": 81.9,
      "by_metric": { "gmv": 39900, "profit": -464411, "fund_balance": 4535589, "initial_fund": 5000000,
                     "conversion": 0.0537, "compliance": 80, "interaction": 325, "fulfillment": 1.0, "orders": 8 } }
  ]
}
```

### 5.12 AI 岗位智能体

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/agents` | 登录 | 市场：内置（全部）/ 班级共享（本班）/ 个人（本人） |
| POST | `/agents` | 登录 | 创建（可从 `from_template_id` 内置模板起步，自动计算完成度） |
| GET | `/agents/{agent_id}` | 可见性校验 | 详情 |
| PATCH | `/agents/{agent_id}` | 创建者 | 修改（审核中/已上架不可改） |
| POST | `/agents/{agent_id}/rehearse` | 创建者 | **预演**（读当前配置与授权场次上下文，不写正式业务、不落库） |
| POST | `/agents/{agent_id}/run` | 见下 | **正式运行**（落库：输入/输出/来源/轨迹/耗时/模型） |
| GET | `/agent-runs` | 登录 | 运行记录（学生仅本人；教师含所带班级任务的记录） |
| POST | `/agent-runs/{run_id}/adopt` | 运行者 | **采纳** `{target: script\|report}` → 写入本人脚本/复盘 |
| POST | `/agent-runs/{run_id}/rating` | 运行者 | 结果评分 1-5 |
| POST | `/agents/{agent_id}/submit` | 创建者 | 提交审核（完成度 < 60% 拒绝） |
| POST | `/agents/{agent_id}/review` | 教师/管理员 | 审核 `{action: approve\|reject, note}`；通过后进班级共享市场 |

`run` 的可运行性：内置/班级共享需 `published`；个人智能体仅创建者可用；班级共享仅本班可用。

**完成度计算**：命名 0.20 + 职责 0.25 + 行为指令 0.35 + 工具配置 0.20。

**POST `/agents/{agent_id}/run`**

```json
// 请求
{ "prompt": "顾客说收到货有破损怎么办？", "context": { "session_id": 3 } }
// 响应（未配置大模型 → 规则兜底，source=rule，caveats 明确声明）
{
  "id": 1, "agent_id": 5, "session_id": 3, "task_id": 4, "user_id": 6,
  "input": { "prompt": "顾客说收到货有破损怎么办？", "context": { "session_id": 3 } },
  "output": {
    "result": "【规则兜底输出·未接入大模型】针对「顾客说收到货有破损怎么办？」：\n客服处理建议（规则模板）…",
    "evidence": ["七天无理由", "发货时效"],
    "caveats": ["当前未配置大模型服务，结果由规则模板生成，仅供教学设计参考"]
  },
  "source": "rule",
  "trace": [{ "step": "context", "keys": ["prompt", "session_id"] }, { "step": "rule_fallback" }],
  "latency_ms": 0, "model": "rule-template",
  "rating_score": null, "adopted_target": null
}
```

**POST `/agent-runs/{run_id}/adopt`**

```json
// 请求
{ "target": "script", "note": "采纳客服话术到脚本" }
// 响应
{ "run_id": 1, "target": "script", "applied_to": { "segments": 0, "adopted_notes": 1 },
  "adopted_at": "2026-10-12T07:28:04Z" }
// 重复采纳返回 409 DUPLICATE；写入目标锁定（复盘已提交）时返回 400 REPORT_LOCKED
```

### 5.13 文件与系统

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/files` | 登录 | 上传文件（白名单扩展名，≤20MB），返回 `{file_id, url}`，通过 `/static/{file_id}` 访问 |
| GET | `/health` | 公开 | 健康检查（含数据库连通状态） |

---

## 6. 附录 A：枚举取值表

| 枚举 | 取值（存储值与中文含义） |
|---|---|
| 用户角色 `role` | `admin` 管理员 / `teacher` 教师 / `student` 学生 |
| 用户状态 `status` | `active` 正常 / `disabled` 已停用（令牌即时失效） |
| 任务状态 | `draft` 草稿 / `published` 已发布 / `closed` 已关闭 |
| 任务模式 | `personal` 个人练习 / `team` 团队协作 |
| 场次状态 | `preparing` 准备中 / `live` 直播中 / `paused` 已暂停 / `ended` 已下播 / `submitted` 已提交 |
| 货盘定位 | `traffic` 引流款 / `profit` 利润款 / `image` 形象款 |
| 货盘商品状态 | `editing` 编辑中 / `listed` 已上架 |
| 团队岗位 | `host` 主播 / `operation` 直播运营 / `control` 场控 / `service` 客服 / `select` 选品 / `ad` 投手 |
| 脚本环节 | `opening` 开场 / `warmup` 暖场 / `explain` 讲解 / `interact` 互动 / `push` 逼单 / `transition` 转场 / `closing` 收尾 |
| 促销类型 | `coupon` 优惠券 / `full_reduction` 满减 / `seckill` 秒杀 / `gift` 赠品 / `lottery` 抽奖 / `group_buy` 拼团 |
| 促销状态 | `active` 生效 / `stopped` 已停止 |
| 投流渠道 | `short_video` 短视频预热 / `feed` 信息流投放 / `reservation` 直播预约 / `social` 社交渠道 |
| 投流目标 | `exposure` 曝光 / `click` 点击 / `enter_room` 进房 / `order` 成交 |
| 投流状态 | `draft` 草稿 / `active` 投放中 / `stopped` 已停止 |
| 直播事件类型 | `metric` 指标 / `speech` 口播 / `behavior` 行为采样 / `comment` 弹幕 / `reply` 回复 / `control` 中控 / `order` 订单 / `violation` 违规 / `ai_decision` AI 决策 / `system` 系统 |
| 口播来源 | `server_asr` 服务端识别 / `browser_asr` 浏览器识别 / `manual` 手动补录 |
| 中控动作 | `switch_item` / `push_coupon` / `seckill` / `lottery` / `announcement` / `poll` / `pin_comment` / `fan_benefit` |
| 订单状态 | `pending_ship` 待发货 / `shipping` 运输中 / `signed` 已签收 / `closed` 已关闭 |
| 物流节点 | `picked_up` 揽收 / `in_transit` 运输中 / `delivering` 派送中 / `signed` 签收 / `rejected` 拒收 |
| 售后类型 | `refund` 退款 / `return` 退货 / `exchange` 换货 / `complaint` 投诉 / `oversell` 超卖 / `delay` 延迟发货 |
| 售后状态 | `pending` 待处理 / `approved` 已同意 / `rejected` 已驳回 / `closed` 已结案 |
| 报告状态 | `draft` 草稿 / `submitted` 已提交 / `returned` 已退回 / `scored` 已评分 |
| 报告来源 | `llm` 大模型生成 / `rule` 规则兜底（**必须明确标识，不得伪装**） |
| 资金流水类型 | `purchase` 采购 / `ad_spend` 投流 / `sales_income` 销售回款 / `refund` 退款 / `adjust` 调整 |
| 智能体范围 | `builtin` 系统内置 / `class` 班级共享 / `personal` 个人创建 |
| 智能体状态 | `draft` 草稿 / `pending` 待审核 / `published` 已上架 / `rejected` 已驳回 |
| 智能体岗位 | `select` 选品 / `operation` 运营 / `control` 场控 / `service` 客服 / `host` 主播 / `teaching` 教学 |
| 竞赛口径 | `gmv` / `profit` / `conversion` / `compliance` / `interaction` / `fulfillment` / `comprehensive` |

## 附录 B：错误码

| 错误码 | HTTP | 含义与典型场景 |
|---|---|---|
| `AUTH_REQUIRED` | 401 | 缺少/无效/过期令牌 |
| `INVALID_CREDENTIALS` | 401/400 | 登录口令错误；修改口令时原口令不符 |
| `ACCOUNT_DISABLED` | 403 | 账号已停用（登录或既有令牌访问时） |
| `PERMISSION_DENIED` | 403 | 越权访问（如学生互读场次、非归属人修改） |
| `NOT_FOUND` | 404 | 资源不存在（班级/任务/场次/订单/报告/成绩等） |
| `DUPLICATE` | 409 | 唯一性冲突（账号、货盘商品、团队成员、重复采纳） |
| `VALIDATION_ERROR` | 422 | 参数校验失败（`context.details` 逐字段说明）或业务参数不合法 |
| `INSUFFICIENT_FUNDS` | 400 | 经营资金不足（采购/投流） |
| `STATE_TRANSITION_INVALID` | 400 | 非法状态迁移（订单/物流/场次/售后/团队解散等） |
| `PREFLIGHT_FAILED` | 400 | 严格任务开播检查未通过（`context.missing` 缺失项） |
| `SESSION_NOT_LIVE` | 400 | 非直播中执行直播操作 / tick |
| `TICK_TOO_FREQUENT` | 429 | tick 间隔小于最小间隔（`context.elapsed_seconds`） |
| `REPORT_LOCKED` | 400 | 复盘已提交锁定，禁止修改/重新生成/采纳写入 |
| `FULFILLMENT_INCOMPLETE` | 400 | 订单未履约或售后未处理完，不允许提交复盘 |
| `AGENT_NOT_PUBLISHED` | 400 | 使用未上架的共享智能体 |
| `AGENT_NOT_APPROVED` | 400 | 智能体状态不允许当前操作（如审核中修改） |
| `ASR_NOT_CONFIGURED` | 501 | 未配置服务端语音识别（前端应降级浏览器识别/手动补录） |
| `EXTERNAL_SERVICE_UNAVAILABLE` | 502 | 外部服务（ASR 等）调用失败 |
| `EXPORT_NOT_IMPLEMENTED` | 501 | 报告导出（Word/PDF）规划中，见附录 C |
| `INTERNAL_ERROR` | 500 | 未捕获的服务端错误（日志含完整堆栈） |

## 附录 C：未实现与后续规划（诚实清单）

以下能力在题目介绍中出现、但本期骨架**未实现**，接口未提供（避免“文档写了、实际没有”）：

| 能力 | 现状 | 后续方案 |
|---|---|---|
| 复盘报告导出 Word/PDF | 未实现 | `GET /sessions/{id}/report/export?format=` 建议接口；服务端模板渲染 |
| 题库与考试（章/题/作答/批改） | 未实现 | 独立模块 `exams`，复用成绩体系 |
| 课程通知与教学资源库 | 未实现 | 已预留 `POST /files` 上传能力，通知可挂班级维度 |
| 移动主播端扫码入会 | 未实现 | 场次级一次性二维码令牌接口 |
| WebSocket 实时推送 | 未实现（用轮询替代） | 保持 `live/events` 事件契约，增量替换推送通道 |
| 数据导出（班级报告 Excel） | 未实现 | 复用班级报告聚合结果导出 |
| 统一身份认证/教务/对象存储对接 | 未实现 | 集成层按院校环境接入（配置化） |

---

## 附录 D：本文档与代码的一致性校验

```bash
cd backend
python scripts/verify_api_doc.py
# 输出：文档接口数 / 代码路由数 / 缺失与多余清单；不一致时退出码非 0
```

> 工作流建议：改接口 → 改本文档 → 跑校验脚本 → 跑 `scripts/smoke_test.py`（含正常/模糊/异常三类场景）。
