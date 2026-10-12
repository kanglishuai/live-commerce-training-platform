# 数据库设计说明（MySQL 8.x）

> 配套实现：`backend/app/models/`（SQLAlchemy 2.0 声明式模型，代码即 Schema 唯一事实源）
> 建表方式：`python scripts/init_db.py`（当前用 `create_all` 幂等建表；生产建议切换 Alembic 迁移）

---

## 1. 设计原则

| 原则 | 落地方式 | 理由 |
|---|---|---|
| 金额零误差 | 所有金额字段 `int`，单位**分**，字段后缀 `_cents` | 规避浮点误差；题目明确要求 |
| 时间统一 | 数据库存 UTC（`DATETIME`），接口序列化补 `Z` | 避免时区歧义；跨端一致 |
| 枚举可演进 | 枚举存 `VARCHAR`（如 `varchar(16)`），取值由应用层 `StrEnum` 校验 | 新增状态不改表结构 |
| 灵活扩展 | 调研/策划/脚本/装修/权重/轨迹等半结构化数据用 `JSON` 列 | 教学场景字段多变，避免宽表爆炸 |
| 场次为核心 | 全部业务数据（货盘/采购/资金/事件/订单/报告/成绩）挂 `sessions.id` | 一次训练 = 一个可追溯闭环 |
| 资金可审计 | 任何余额变化写 `fund_txns` 流水，含变动后余额 | 复盘与争议可回查 |
| 过程可回溯 | 直播全量事件写 `live_events`（自增 id 作前端增量游标） | 报告与 AI 决策可复核 |

## 2. 表总览（20 张）

| 域 | 表 | 说明 |
|---|---|---|
| 用户体系 | `users` | 管理员/教师/学生三级账号（`role`），学生 `class_id` 归属 |
| | `classes` | 班级（教学组织边界），`teacher_id` 班主任 |
| | `teams` | 实训团队（小组），`invite_code` 邀请码 |
| | `team_members` | 团队成员与岗位（`position`），`(team_id, user_id)` 唯一 |
| 任务场次 | `tasks` | 任务（资金/热度/难度/严格模式/评分权重/智能体作业） |
| | `sessions` | 场次：状态机、资金余额、调研/策划/脚本/装修 JSON、实时快照 `metrics` |
| 商品与经营 | `products` | 商品库（内置 + 自定义），成本/市场价/热度/库存 |
| | `session_items` | 场次货盘：定位(引流/利润/形象)、图文卖点、划线价/直播价、采购与库存 |
| | `purchases` | 采购单（供应商/数量/单价/总额） |
| | `fund_txns` | 资金流水（采购/投流/回款/退款），含 `balance_after_cents` |
| | `promotions` | 促销配置（券/满减/秒杀/赠品/拼团/抽奖） |
| | `ad_plans` | 投流计划（渠道/预算/已消耗/人群/出价/优化目标） |
| 直播与履约 | `live_events` | 直播事件流（口播/行为/弹幕/回复/中控/订单/违规/AI 决策/指标） |
| | `orders` | 模拟订单（状态机 + 物流节点 + 物流轨迹 JSON） |
| | `after_sales` | 售后工单（类型/金额/处理意见/状态机） |
| 评价 | `reports` | 复盘报告（结构化内容 JSON、来源 llm/rule、锁定态、改进措施） |
| | `scores` | 成绩（客观分+五维明细/权重快照/主观分/综合分/评分教师） |
| | `competitions` | 竞赛（口径 metric、规则、状态） |
| 智能体 | `agents` | 智能体配置（职责/指令/技能/工具/知识卡/完成度/范围/审核状态） |
| | `agent_runs` | 运行记录（输入/输出/来源/轨迹/耗时/模型/评分/采纳目标） |

关系主线：

```
classes ─┬─ users(students) ─┬─ team_members ── teams
         │                   └─ sessions(owner) ─┬─ session_items ── orders ── after_sales
         └─ tasks ── sessions ─────────────────┬─ purchases / fund_txns / promotions / ad_plans
                                               ├─ live_events
                                               ├─ reports ── scores
                                               └─ agent_runs(可空关联) ── agents
competitions（班级/任务维度，排行榜由 sessions+scores 聚合计算）
```

## 3. 关键表字段与约束

### 3.1 `sessions`（场次，业务核心）

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | varchar(16) | preparing / live / paused / ended / submitted（状态机见 docs/API.md §4） |
| `fund_balance_cents` | int | 当前经营资金余额；初值取任务 `initial_fund_cents`；大写场景用行锁保障 |
| `research` / `plan` / `script` / `room_config` | json | 各环节提交物（结构见 API 文档） |
| `metrics` | json | 实时快照：online/viewers/likes/comments/item_clicks/orders/gmv_cents/tick_count/last_tick_at/ad_spend_cents/last_event_id |
| `started_at` / `ended_at` / `submitted_at` | datetime | 关键时间点，用于时长与及时率统计 |

索引：`task_id`、`owner_id`、`team_id`、`status`。

### 3.2 `live_events`（事件流）

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | varchar(32) | metric / speech / behavior / comment / reply / control / order / violation / ai_decision / system |
| `payload` | json | 按类型承载内容（口播文本、弹幕、订单号、动作、决策输入摘要等） |
| `source` | varchar(32) | rule / llm / manual / server_asr / browser_asr / client_local —— **来源必须可辨识** |

索引：`session_id`、`(session_id, id)`、`type`、`ts`。自增 `id` 同时充当前端增量拉取游标（`since_id`）。
数据量策略：教学场景单场约数百条；后续可按学期归档或按 `session_id` 分区。

### 3.3 `orders` 与 `after_sales`

- `orders.logistics_history`（json）：`[{node, at, note}]` 轨迹数组；`logistics_node` 冗余当前节点便于筛选。
- 约束靠状态机（应用层）保证：非法迁移在 `services/state_machines.py` 拒绝（拒绝重复发货、状态回退）。
- `after_sales.amount_cents`：退款类默认订单全额，允许余额为负（应退必退）。

### 3.4 `scores`（成绩可复查）

`objective_detail`（json）保存**评分时的维度分、权重、客观占比与证据快照**，`weights` 冗余一份；
教师复查或跨场次对比时口径一致（题目 5.4 要求）。

### 3.5 `agents` / `agent_runs`

- `agents.completeness`：命名 0.20 + 职责 0.25 + 行为指令 0.35 + 工具 0.20（提交审核需 ≥0.6）。
- `agent_runs.source` 区分 `llm` / `rule`；`adopted_target` 记录是否被采纳进脚本/复盘（「先生成、后采纳」）。

## 4. MySQL 部署要点

```sql
-- 建库（utf8mb4 全量字符集，支持 emoji 与生僻字）
CREATE DATABASE IF NOT EXISTS live_training
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

- 连接串：`mysql+pymysql://<user>:<password>@<host>:3306/live_training?charset=utf8mb4`（见 `backend/.env`）。
- 驱动：PyMySQL（纯 Python）+ cryptography（MySQL 8 `caching_sha2_password` 认证需要）。
- 命名规避保留字：小组表命名 `teams`（避免 `groups` 在 MySQL 8 的保留字问题）。
- 资金类写操作用 `SELECT ... FOR UPDATE` 行锁（SQLite 测试环境自动忽略该子句，模型保持双方言可移植）。
- 连接池：`pool_pre_ping=True`、`pool_recycle=3600`（规避 MySQL `wait_timeout` 断连）。

## 5. 已知限制与演进方向

| 项 | 现状 | 演进 |
|---|---|---|
| 建表方式 | `create_all`（幂等，无版本管理） | 引入 Alembic 迁移 |
| 事件表体量 | 单表，无归档 | 按学期/场次归档或分区 |
| 全文检索 | 商品名 `LIKE` 查询 | 需要时接 MySQL 全文索引或 Elasticsearch |
| 文件存储 | 本地 `backend/var/uploads` | 对象存储（题目预留扩展点） |
| 并发规模 | 面向课堂（每班数十人） | 行锁已就绪；更大规模可加 Redis 限流/缓存 |
