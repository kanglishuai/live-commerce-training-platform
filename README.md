# 直播运营虚拟仿真实训平台（骨架版 v0.1.0）

面向职业院校与实训基地的直播电商全流程教学平台。本仓库为**限时实践任务的骨架交付**：
后端可运行、数据库可建表、核心业务闭环（发布任务 → 经营准备 → 仿真开播 → 履约售后 → 复盘评分）端到端跑通并有自动化用例；
前端提供可运行的工程骨架与主要页面。

> 平台中的观众、订单、资金、物流均为**教学仿真数据**，不连接真实支付，不产生真实交易。

## 仓库结构

```
├── AGENTS.md                 # 人机协作约束（任务信息、时间盒、红线）
├── README.md                 # 本文件
├── 探索记录.md                # 未知项验证过程（交付物之一）
├── docs/
│   ├── API.md                # 接口文档（114 接口，含权限/状态机/枚举/错误码）
│   └── DATABASE.md           # 数据库设计说明（20 张表）
├── backend/                  # FastAPI + SQLAlchemy + MySQL
│   ├── app/                  # core(配置/安全/依赖) models schemas services api prompts
│   ├── scripts/
│   │   ├── init_db.py        # 建表 + 演示数据（幂等）
│   │   ├── smoke_test.py     # 端到端冒烟测试（64 用例，正常/模糊/异常三类场景）
│   │   └── verify_api_doc.py # 接口文档与代码路由一致性校验
│   ├── requirements.txt
│   └── .env.example
└── frontend/                 # Vue 3 + TS + Vite + Pinia + Router
    └── src/                  # api(stores/router/layouts/views) —— 见下方“前端骨架”
```

---

## 1. 启动说明

### 1.1 前置条件

- Python ≥ 3.12（本机实测 3.13.13）
- MySQL 8.x（本机实测 8.4.9，服务已启动）
- Node ≥ 18（本机实测 24，仅前端需要）

### 1.2 数据库准备（一次性）

```bash
# 建库（utf8mb4）
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS live_training DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 1.3 后端（在 backend/ 目录）

```bash
cd backend
python -m pip install -r requirements.txt        # 建议使用虚拟环境

# 配置：复制模板并填写本机 MySQL 口令与随机密钥
cp .env.example .env
#   DATABASE_URL=mysql+pymysql://root:<你的口令>@127.0.0.1:3306/live_training?charset=utf8mb4
#   SECRET_KEY=<python -c "import secrets;print(secrets.token_urlsafe(32))">

python scripts/init_db.py                        # 建表 + 演示数据（幂等）
python scripts/smoke_test.py                     # 端到端冒烟测试（全部通过退出码 0）
uvicorn app.main:app --reload --port 8000        # 启动服务
```

- 接口文档 UI：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/health

### 1.4 前端（在 frontend/ 目录）

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 ，已配置 /api 与 /static 代理到 8000
```

> 依赖已在本机安装完成（142 个包），`npm run build`（vue-tsc 类型检查 + vite 构建）已跑通。

### 1.5 演示账号（种子数据）

| 角色 | 账号 | 口令 |
|---|---|---|
| 管理员 | `admin` | `Admin@123` |
| 教师（电商2301 班） | `teacher_li` | `Teacher@123` |
| 学生（电商2301 班） | `stu_001` ～ `stu_010` | `Student@123` |
| 教师（电商2302 班） | `teacher_wang` | `Teacher@123` |

种子数据还包含：12 款助农商品、2 个任务（1 个普通、1 个严格模式的竞赛训练任务）、4 个内置岗位智能体、2 个团队。

---

## 2. 已验证 / 未验证（诚实标注）

### 2.1 已验证（可复现命令 + 实测输出）

| 项 | 命令 | 实测结果 |
|---|---|---|
| MySQL 建表 | `python scripts/init_db.py` | 20 张表创建成功；种子数据写入 `{"seeded": true, "class": "电商2301班", ...}` |
| 表结构核对 | `mysql -u root -p live_training -e "SHOW TABLES"` | 20 张表：users/classes/teams/team_members/tasks/sessions/products/session_items/purchases/fund_txns/promotions/ad_plans/live_events/orders/after_sales/reports/scores/competitions/agents/agent_runs |
| **端到端冒烟** | `python scripts/smoke_test.py` | **64/64 通过**（退出码 0），覆盖：登录/越权/建课发任务/调研/选品/采购（含超预算拒绝）/定价/脚本/投流/装修/开播检查/开播/6 个仿真周期（实测 viewers=382、gmv=39900 分）/AI 观众弹幕/敏感词违规/中控切换/下播/订单履约（含状态回退拒绝）/售后退款回补/复盘生成（source=rule）/未履约拦截/提交锁定/教师评分（综合分 84.3）/班级报告/巡课/数据罗盘 4 视角/竞赛排行榜/智能体全流程（创建→预演不落库→运行落库→采纳写入→提交审核→教师上架）/严格任务阻断/停用账号令牌即时失效 |
| 接口文档一致性 | `python scripts/verify_api_doc.py` | **文档 114 个接口 = 代码 114 条路由，完全一致** |
| LLM 降级路径 | 冒烟测试（未配置 `LLM_*` 时） | 复盘报告与智能体均返回 `source=rule` 且内容明确标注“规则兜底/未接入大模型” |
| **大模型已接入（DeepSeek `deepseek-flash`）** | `python scripts/smoke_test.py`（配置 `backend/.env` 后） | **67/67 通过**（1 分 28 秒，含 6 次真实模型调用）：回复建议 `source=llm`；复盘报告 `source=llm` 且内容引用真实指标；智能体运行 `source=llm`、`model=deepseek-flash`、耗时 6.9s；AI 观众每 2 个 tick 调用一次（库内：弹幕 llm 9 条 / rule 32 条，决策 llm 3 条 / rule 27 条）；旧数据仍保留 `rule` 标识，两种来源可区分 |
| 前端类型检查与构建 | `cd frontend && npm run build` | `vue-tsc --noEmit` 无报错，`vite build` 成功（120 模块，出口 ~160KB gzip 60KB） |
| 前端浏览器联调 | 浏览器实机访问 `localhost:5173`（后端 + Vite 代理同时运行） | 登录页渲染与路由守卫（未登录跳 `/login`）✅；stu_001 登录成功 ✅；**首页**任务列表（含种子任务与严格竞赛任务）与场次列表（真实仿真数据：已提交场次 45,355.89 元 / 382 观看 / 8 单）✅；**经营准备页**（`/workbench/7`：6 个 Tab、调研表单、资金余额 30,000.00 元 来自 MySQL）✅；**数据复盘页**（`/review/2`：指标卡 382/149/8/399.00 元、规则兜底报告全文、成绩 客观 81.9 + 主观 88 = 综合 84.3、提交后输入框锁定）✅。联调中发现并修复 2 处 UI 问题（锁定时间显示为 `true`、状态标签未本地化），修复后重新构建通过 |

### 2.2 未验证 / 未实现（宁诚实勿含糊）

| 项 | 状态 | 说明 |
|---|---|---|
| 服务端语音识别（ASR） | **未接** | 接口存在，未配置时返回 `501 ASR_NOT_CONFIGURED`（前端应降级浏览器识别/手动补录） |
| 浏览器语音识别 / 人脸出镜采样 | **未实现** | 前端为骨架占位（行为采样按钮仅验证接口链路，UI 已明确标注） |
| 直播间画布（元素拖拽/实时预览） | **简化实现** | 骨架版保存标题/公告/敏感词/画布 JSON 即可满足开播检查；专业直播伴侣画布为后续迭代 |
| 直播工作台页面内的按钮点击回放 | **受环境限制未逐项点击** | 自动化浏览器在本机无法完成指针点击（填充输入正常），页面通过路由直达 + DOM 快照验证；真实点击交互建议人工过一遍 |
| 报告导出 Word/PDF、题库考试、课程通知、移动端扫码、WebSocket | **未实现** | 已在 `docs/API.md 附录 C` 列出建议接口与后续方案 |

---

## 3. 核心闭环体验路径（对应题目 19.1 / 19.2 演示场景）

1. 教师（teacher_li）登录 → 任务与场次 → 新建任务（默认配置）→ 自动发布；
2. 学生（stu_001）登录 → 对该任务「创建场次」→ 进入**经营准备**：
   市场调研 → 货盘加入 3 款（引流/利润/形象）→ 采购 → 定价 → 脚本 → 投流 → 装修；
3. 「开播检查」页核验 9 项 → 开始直播 → **直播工作台**：勾选自动推进（每 2.5 秒一个仿真周期），
   观察在线/点击/订单/GMV 变化，AI 观众弹幕、口播（含敏感词违规）、中控切换商品、AI 回复建议；
4. 下播 → **订单履约**：发货 → 揽收/运输/派送/签收（或拒收），发起售后并处理（退款回补库存）；
5. **数据复盘**：生成报告（规则兜底，`source=rule`）→ 填写改进措施 → 提交（锁定）；
6. 教师：教师侧「班级与巡课」查看巡课看板与班级报告 → 在复盘页录入主观分 → 得到综合成绩；
7. 竞赛：教师创建竞赛（口径 comprehensive）→ 查看排行榜；学生可在**智能体中心**设计客服智能体 →
   预演 → 正式运行 → 采纳写入脚本 → 提交审核 → 教师上架到班级市场。

---

## 4. 关键设计决策（为什么选它、放弃了什么）

| 决策 | 选择 | 放弃/代价 |
|---|---|---|
| 实时仿真驱动 | 前端定频调用 `POST /live/tick`（服务端最小间隔防刷，种子取自场次+周期号，可复现） | 放弃 WebSocket/消息队列：换来零中间件依赖、可暂停演示；后续可平滑替换推送通道 |
| 认证 | JWT(HS256) + PBKDF2-SHA256（stdlib） | 放弃 bcrypt/argon2 依赖（Windows 构建风险）；生产应替换为 argon2 |
| 角色存储 | `VARCHAR` + 应用层 `StrEnum` 校验 | 放弃数据库原生 ENUM：新增状态零改表 |
| 金额 | 全链路整数「分」 | —（题目明确要求） |
| 小组表命名 | `teams` | 规避 MySQL 8 保留字 `groups` |
| 建表 | `create_all` 幂等 + 种子脚本 | 放弃 Alembic 迁移（时间盒内）；生产必须补 |
| AI 能力 | 统一适配层：超时 + JSON 解析防御 + **规则兜底且 source 明确标识**；AI 观众在 tick 内**降频调用**（每 2 周期一次 + 10s 超时），避免推理模型拖慢直播节奏 | 模型不可用时功能“可用但降级”，绝不把规则结果伪装成 AI |

---

## 5. AI 参与说明

```
AI 参与说明：
- 使用 ZCode（AI 编码助手）完成：后端全部代码骨架（模型/服务/接口/脚本）、接口文档与数据库设计初稿、
  前端工程骨架与页面初稿、冒烟测试用例编写与调试；人工完成：需求理解与拆解、技术选型拍板、
  MySQL 环境与口令提供、模板文件整理、关键约束（金额分存储/状态机/角色边界/仿真数据边界）的确认。
- 关键设计决策（见第 4 节：前端 tick 驱动仿真、JWT+PBKDF2、teams 命名、规则兜底明确标识）
  为人工判断并验证。
- 完全由人工完成的部分：面试题目文档的提供与解读方向、演示范围取舍（19.1–19.4 场景优先级）、
  数据库账号与部署环境准备。
```

## 6. 后续计划（时间盒外的顺延项）

1. 直播间画布（拖拽/实时预览/摄像头合成）与浏览器 ASR、人脸出镜采样；
2. Alembic 迁移、报告导出（Word/PDF）、题库考试与课程通知；
3. 提示词效果评估与 AI 观众策略调优（接入 DeepSeek 后已回归 `source=llm` 路径）。
