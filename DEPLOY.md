# 抖音本地推投流分析 Agent — 部署文档

## 一、项目概述

本项目是一个抖音来客「本地推」投流数据分析与优化系统，通过巨量引擎 Open API v3.0 自动拉取多账户广告数据，提供素材决策、异常检测、KPI 分析和可视化看板。

**核心能力**：三级报表同步（账户/项目/素材）→ 四象限决策引擎 → Web 看板 → CLI 自然语言查询 → 告警推送

---

## 二、环境要求

| 组件 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.10+ | 推荐 3.12+，需支持 `str \| None` 语法 |
| 操作系统 | macOS / Linux / Windows | macOS/Linux 优先，daemon 模式仅限 Unix |
| 网络 | 可访问 `api.oceanengine.com` | 需开通巨量引擎开放平台权限 |
| 磁盘 | ~200MB | 代码+依赖 ~50MB，数据库 ~150MB（30天数据） |

---

## 三、前置条件：巨量引擎开放平台配置

### 3.1 创建应用

1. 登录 [巨量引擎开放平台](https://open.oceanengine.com/)
2. 进入「开发者」→「应用管理」→ 创建应用
3. 记录以下信息：
   - **App ID**（应用ID）
   - **Secret**（应用密钥）
4. 应用需开通权限：
   - `本地推报表查询` — `local/report/account/get/`、`local/report/promotion/get/`、`local/report/material/get/`
   - `广告主信息查询` — `advertiser/info/`
   - `OAuth2.0 授权`

### 3.2 获取 BP 账户 ID

- BP 管理账户 ID：在巨量引擎后台 → 工具 → 账户管理中查看
- 子账户 ID：通过 BP 账户下的子账户列表获取（或运行 `python main.py sync` 自动发现）

### 3.3 获取 Access Token（两种方式）

**方式一：直接预配置 Token（简单）**

从巨量引擎后台或已有项目中获取 Access Token，直接写入 `.env`。

**方式二：OAuth2 授权流程（标准）**

```bash
python main.py auth
# → 浏览器打开授权链接
# → 登录并授权
# → 从回调地址栏复制 auth_code
# → python main.py auth --code <auth_code>
```

---

## 四、部署步骤

### 4.1 获取代码

将项目目录完整复制到目标机器：

```bash
# 方式一：直接拷贝整个目录
cp -r douyin-local-ad-agent /目标路径/

# 方式二：打包传输
cd /Users/selfgrowing/WorkBuddy/2026-06-22-23-51-30
tar czf douyin-local-ad-agent.tar.gz \
  --exclude='data/ad_data.db' \
  --exclude='data/.token_cache.json' \
  --exclude='__pycache__' \
  --exclude='.env' \
  douyin-local-ad-agent/
# 传输后在目标机器解压
tar xzf douyin-local-ad-agent.tar.gz
```

> **注意**：默认不拷贝 `.env`（含密钥）和 `data/ad_data.db`（数据库），目标机器需重新配置和拉取数据。

### 4.2 创建 Python 虚拟环境

```bash
cd douyin-local-ad-agent

# 创建虚拟环境
python3 -m venv venv

# 激活
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate          # Windows
```

### 4.3 安装依赖

```bash
pip install -r requirements.txt
```

依赖清单（仅 3 个核心包）：
- `flask>=3.0` — Web 看板
- `requests>=2.31` — API 调用
- `apscheduler>=3.10` — 定时同步
- `pandas>=2.0` — 数据处理

### 4.4 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填写以下 **必填** 项：

```ini
# ── 必填 ──
OCEAN_ENGINE_APP_ID=你的AppID
OCEAN_ENGINE_SECRET=你的Secret
OCEAN_ENGINE_LOCAL_ACCOUNT_ID=你的BP账户ID

# ── Token（二选一）──
# 方式一：直接填已有 Token（推荐快速部署）
OCEAN_ENGINE_ACCESS_TOKEN=你的access_token

# 方式二：通过 OAuth 授权获取（见 3.3 节）
# OCEAN_ENGINE_AUTH_CODE=你的授权码

# ── 可选：告警推送 ──
# WECOM_WEBHOOK_URL=企业微信群机器人Webhook
# FEISHU_WEBHOOK_URL=飞书群机器人Webhook
```

### 4.5 配置子账户（重要）

编辑 `config/settings.py`，在 `LOCAL_SUB_ACCOUNTS` 中填写所有需要监控的子账户：

```python
LOCAL_SUB_ACCOUNTS: dict[str, str] = {
    "01成都店":   "1839326360573324",
    "02重庆店":   "1865594502878474",
    # ... 添加你的所有子账户
}
LOCAL_SUB_ACCOUNT_IDS = list(LOCAL_SUB_ACCOUNTS.values())
```

> **同步双文件**：`config/settings.py` 和 `src/config/settings.py` 两个文件都需要包含相同的 `LOCAL_SUB_ACCOUNTS` 配置。项目代码中 daemon 用 `sys.path.insert(0, PROJECT_ROOT)` 会优先解析根目录的 `config/settings.py`，两个文件必须保持一致。

### 4.6 授权（如果使用 OAuth 方式）

```bash
python main.py auth
# 按提示在浏览器中授权，获取 auth_code 后：
python main.py auth --code <你的auth_code>
```

### 4.7 首次拉取数据

```bash
# 拉取最近 30 天数据
python backfill_30d.py
# 或指定天数
python main.py backfill 30
```

### 4.8 启动看板

```bash
# 方式一：前台启动（推荐调试时用）
python main.py dashboard --port 8888

# 方式二：后台守护进程（推荐长期运行）
python daemon_launch.py

# 方式三：一键脚本
./start_dashboard.sh
```

启动后访问：**http://localhost:8888**

---

## 五、项目结构

```
douyin-local-ad-agent/
├── .env                    # 环境变量（密钥，不提交）
├── .env.example            # 环境变量模板
├── requirements.txt        # Python 依赖
├── main.py                 # CLI 入口（dashboard/sync/backfill/query/report/alerts）
├── daemon_launch.py        # 后台守护进程启动器
├── start_dashboard.sh      # 一键启动脚本
├── backfill_30d.py         # 30天数据回填脚本
├── config/
│   └── settings.py         # 全局配置（账户列表、API参数、规则）
├── data/
│   ├── ad_data.db          # SQLite 数据库（自动创建）
│   └── .token_cache.json   # Token 缓存（自动创建）
├── outputs/                # 报告输出目录
└── src/
    ├── api/
    │   ├── auth.py          # OAuth2 认证 + Token 自动刷新
    │   └── client.py        # 巨量引擎 API 客户端
    ├── pipeline/
    │   ├── etl.py           # ETL 管道（三级报表同步）
    │   ├── storage.py       # SQLite 存储层（建表+CRUD）
    │   └── scheduler.py     # APScheduler 定时同步
    ├── analysis/
    │   ├── kpi.py           # KPI 分析（汇总/趋势/排行）
    │   ├── anomaly.py       # 异常检测
    │   ├── material_decision.py   # 素材决策引擎（四象限+效率分）
    │   ├── material_analysis.py   # 素材深度分析（疲劳/浪费/分布）
    │   └── attribution.py   # 归因分析框架
    ├── optimization/
    │   └── engine.py        # 优化建议引擎
    ├── agent/
    │   └── agent.py         # CLI Agent（自然语言查询+报告生成+告警）
    ├── web/
    │   ├── app.py           # Flask 看板（4-Tab）
    │   └── static/          # 静态资源
    └── config/
        └── settings.py      # 配置副本（需与根目录 config/ 保持一致）
```

---

## 六、数据库 Schema

| 表名 | 说明 | 主键/唯一约束 |
|------|------|-------------|
| `accounts` | 账户元信息 | `account_id` |
| `account_reports` | 账户日报表 | `UNIQUE(account_id, stat_date)` |
| `promotion_reports` | 项目（投放计划）日报表 | `UNIQUE(account_id, promotion_id, stat_date)` |
| `material_reports` | 素材日报表 | `UNIQUE(account_id, material_id, stat_date)` |
| `optimization_log` | 优化建议记录 | `id` 自增 |

索引：`idx_ar_account_date`、`idx_ar_date`、`idx_pr_account_date`、`idx_mr_account_date`、`idx_mr_material`

数据库首次运行自动创建，无需手动建表。

---

## 七、常用命令速查

| 命令 | 用途 |
|------|------|
| `python main.py dashboard` | 启动 Web 看板（默认 8888 端口） |
| `python main.py dashboard --port 9000` | 指定端口启动 |
| `python main.py auth` | OAuth 授权向导 |
| `python main.py auth --code <code>` | 用授权码换取 Token |
| `python main.py sync` | 同步昨日数据 |
| `python main.py sync --date 2026-06-25` | 同步指定日期数据 |
| `python main.py backfill 30` | 回填最近 30 天数据 |
| `python main.py query "素材分析"` | 自然语言查询 |
| `python main.py query "哪个素材CPA最低"` | 素材排行 |
| `python main.py query "素材ID 1234567890123456"` | 查看单素材详情 |
| `python main.py query "异常"` | 异常检测 |
| `python main.py query "优化"` | 优化建议 |
| `python main.py report` | 生成日报 |
| `python main.py report --weekly` | 生成周报 |
| `python main.py alerts` | 检查异常并推送告警 |
| `python daemon_launch.py` | 后台守护进程启动 |

---

## 八、AI 工具部署指南（WorkBuddy / Claude Code 等）

如果要在 AI 编程工具中部署此项目，将以下内容提供给 AI：

### 8.1 最小部署提示词

```
请帮我部署「抖音本地推投流分析 Agent」项目。

项目路径：<你的项目目录路径>

部署步骤：
1. 在项目目录创建 Python 虚拟环境: python3 -m venv venv && source venv/bin/activate
2. 安装依赖: pip install -r requirements.txt
3. 复制 .env.example 为 .env，填写以下配置:
   - OCEAN_ENGINE_APP_ID=<你的AppID>
   - OCEAN_ENGINE_SECRET=<你的Secret>
   - OCEAN_ENGINE_LOCAL_ACCOUNT_ID=<BP账户ID>
   - OCEAN_ENGINE_ACCESS_TOKEN=<已有Token>
4. 确认 config/settings.py 中 LOCAL_SUB_ACCOUNTS 包含正确的子账户映射
5. 运行 python main.py backfill 30 拉取30天历史数据
6. 运行 python main.py dashboard --port 8888 启动看板
7. 浏览器访问 http://localhost:8888

关键注意事项:
- config/settings.py 和 src/config/settings.py 必须保持一致
- 账户信息通过 API 动态获取，不要依赖静态文件
- Token 缓存在 data/.token_cache.json，过期自动刷新
- daemon_launch.py 中 PROJECT_DIR 需改为实际部署路径
```

### 8.2 给 AI 的上下文文件

部署时建议让 AI 阅读以下文件（按优先级排序）：

1. `本文件`（DEPLOY.md）— 部署全流程
2. `.env.example` — 环境变量模板
3. `config/settings.py` — 全局配置和账户列表
4. `main.py` — CLI 入口和命令说明
5. `requirements.txt` — 依赖清单
6. `src/pipeline/storage.py` 前 120 行 — 数据库 Schema

---

## 九、配置项详解

### 9.1 `.env` 环境变量

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `OCEAN_ENGINE_APP_ID` | 是 | 开放平台应用 ID |
| `OCEAN_ENGINE_SECRET` | 是 | 开放平台应用密钥 |
| `OCEAN_ENGINE_LOCAL_ACCOUNT_ID` | 是 | BP 管理账户 ID |
| `OCEAN_ENGINE_ACCESS_TOKEN` | 二选一 | 直接填写已有 Token |
| `OCEAN_ENGINE_AUTH_CODE` | 二选一 | OAuth 授权码（一次性） |
| `OCEAN_ENGINE_REDIRECT_URI` | 否 | OAuth 回调地址（默认即可） |
| `WECOM_WEBHOOK_URL` | 否 | 企业微信告警 Webhook |
| `FEISHU_WEBHOOK_URL` | 否 | 飞书告警 Webhook |

### 9.2 `config/settings.py` 关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `BP_ACCOUNT_ID` | `"1858351921937411"` | BP 管理账户 ID |
| `LOCAL_SUB_ACCOUNTS` | 28个账户 | 子账户名称→ID 映射 |
| `SCHEDULE_INTERVAL_MINUTES` | `30` | 自动同步间隔（分钟） |
| `ANOMALY_THRESHOLD_PCT` | `30` | 异常波动阈值（%） |
| `ANOMALY_MIN_COST` | `100` | 最小消耗阈值（低于不告警） |
| `ANOMALY_LOOKBACK_DAYS` | `7` | 异常检测回溯天数 |
| `TOKEN_REFRESH_BUFFER` | `3600` | Token 过期前刷新缓冲（秒） |
| `DASHBOARD_REFRESH_SECONDS` | `300` | 看板自动刷新间隔（秒） |

### 9.3 优化规则 `OPT_RULES`

可在 `config/settings.py` 中自定义规则：

```python
OPT_RULES = {
    "low_roi_pause": {
        "condition": "cost > 500 AND roi < 0.8",
        "action": "suggest_pause",
        "reason": "消耗大于500元但ROI低于0.8，建议暂停",
    },
    "high_roi_scale": { ... },
    "high_cpa_warning": { ... },
    "low_ctr_creative": { ... },
}
```

---

## 十、验证部署成功

按以下顺序验证：

```bash
# 1. 验证 Python 环境
python --version          # 应 >= 3.10
pip list                  # 确认 flask, requests, apscheduler, pandas 已安装

# 2. 验证 .env 配置
python -c "
from main import _load_dotenv; _load_dotenv()
import os
print('APP_ID:', os.getenv('OCEAN_ENGINE_APP_ID', 'MISSING'))
print('LOCAL_ACCOUNT_ID:', os.getenv('OCEAN_ENGINE_LOCAL_ACCOUNT_ID', 'MISSING'))
print('TOKEN:', 'SET' if os.getenv('OCEAN_ENGINE_ACCESS_TOKEN') else 'MISSING')
"

# 3. 验证 API 连通性（拉取1天数据）
python main.py sync --date 2026-06-25
# 应输出: Synced N rows

# 4. 验证数据库
python -c "
import sqlite3
conn = sqlite3.connect('data/ad_data.db')
for t in ['accounts','account_reports','promotion_reports','material_reports']:
    c = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {c} rows')
conn.close()
"

# 5. 启动看板
python main.py dashboard --port 8888
# 浏览器访问 http://localhost:8888，应看到4-Tab看板
```

---

## 十一、常见问题

### Q1: Token 过期怎么办？

Token 自动刷新机制会在过期前 1 小时自动刷新。如果刷新失败（如 refresh_token 也过期）：
```bash
python main.py auth          # 重新获取授权链接
python main.py auth --code <新授权码>
```

### Q2: 看板启动后没有数据？

1. 检查 `data/ad_data.db` 是否存在
2. 运行 `python main.py backfill 30` 拉取历史数据
3. 检查 `.env` 中 Token 是否有效
4. 查看 `/tmp/dashboard.log` 日志

### Q3: 子账户数据不全？

1. 确认 `config/settings.py` 中 `LOCAL_SUB_ACCOUNTS` 包含所有子账户
2. **同时检查** `src/config/settings.py` 是否同步（双文件 Bug）
3. 账户 ID 必须为 16 位数字，过短/过长都会导致 API 报错

### Q4: daemon_launch.py 路径错误？

`daemon_launch.py` 中 `PROJECT_DIR` 是硬编码的绝对路径，换机器后需修改：
```python
PROJECT_DIR = "/你的实际部署路径/douyin-local-ad-agent"
```

### Q5: Windows 上 daemon 模式不可用？

`daemon_launch.py` 使用 Unix `fork()` 双 fork 守护进程，Windows 不支持。Windows 上请用前台模式：
```bash
python main.py dashboard --port 8888
```
或使用 `pythonw.exe` 后台运行。

### Q6: 如何迁移已有数据库？

直接拷贝 `data/ad_data.db` 到新部署的 `data/` 目录即可。SQLite 是单文件数据库，无需额外操作。Token 缓存 `data/.token_cache.json` 也可一并拷贝。

---

## 十二、告警推送配置（可选）

### 企业微信

1. 企业微信群 → 右上角 `...` → 群机器人 → 添加
2. 复制 Webhook 地址，填入 `.env`：
   ```
   WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
   ```

### 飞书

1. 飞书群 → 设置 → 群机器人 → 添加机器人
2. 复制 Webhook 地址，填入 `.env`：
   ```
   FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
   ```

配置后运行 `python main.py alerts` 测试推送。

---

## 十三、附：当前部署环境信息

| 项目 | 值 |
|------|-----|
| 应用名 | 三老板投流监测 |
| App ID | 1865418250102980 |
| BP 账户 ID | 1858351921937411 |
| 子账户数量 | 28 个 |
| 数据日期范围 | 2026-05-27 ~ 2026-06-26 |
| 数据库大小 | ~40,902 条素材记录 |
| 看板端口 | 8888 |
| 同步频率 | 每 30 分钟 |
| Python 版本 | 3.13.12 |

---

*文档更新日期：2026-06-26*
