"""
Configuration for Douyin Local Ad Analysis Agent

Set credentials via environment variables:
  OCEAN_ENGINE_APP_ID
  OCEAN_ENGINE_SECRET
  OCEAN_ENGINE_ADVERTISER_ID
  OCEAN_ENGINE_ACCESS_TOKEN  (optional, if already obtained)
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Ocean Engine API ──────────────────────────────────────────
OCEAN_ENGINE_APP_ID = os.getenv("OCEAN_ENGINE_APP_ID", "")
OCEAN_ENGINE_SECRET = os.getenv("OCEAN_ENGINE_SECRET", "")
OCEAN_ENGINE_ADVERTISER_ID = os.getenv("OCEAN_ENGINE_ADVERTISER_ID", "")
OCEAN_ENGINE_LOCAL_ACCOUNT_ID = os.getenv("OCEAN_ENGINE_LOCAL_ACCOUNT_ID", "")
OCEAN_ENGINE_ACCESS_TOKEN = os.getenv("OCEAN_ENGINE_ACCESS_TOKEN", "")

# API Base URLs
OCEAN_ENGINE_API_BASE = "https://api.oceanengine.com/open_api"
OCEAN_ENGINE_API_V3_BASE = "https://api.oceanengine.com/open_api/v3.0"  # v3.0 (本地推API)
OCEAN_ENGINE_AUTH_URL = "https://api.oceanengine.com/open_api/oauth2"
OCEAN_ENGINE_REDIRECT_URI = os.getenv("OCEAN_ENGINE_REDIRECT_URI", "https://www.example.com/callback")
OCEAN_ENGINE_AUTH_CODE = os.getenv("OCEAN_ENGINE_AUTH_CODE", "")

# Token refresh buffer (seconds before expiry to refresh)
TOKEN_REFRESH_BUFFER = 3600

# ── Database ──────────────────────────────────────────────────
DATABASE_PATH = str(DATA_DIR / "ad_data.db")

# ── Report Defaults (标准营销API v2) ─────────────────────────
DEFAULT_REPORT_METRICS = [
    "cost",              # 消耗
    "show",              # 展示量
    "click",             # 点击量
    "convert",           # 转化数
    "ctr",               # 点击率
    "cvr",               # 转化率
    "cpa_platform",      # 转化成本
    "click_cnt",         # 点击数 (精确)
    "show_cnt",          # 展示数 (精确)
    "stat_cost",         # 消耗 (精确)
]

DEFAULT_REPORT_DIMENSIONS = [
    "advertiser_id",
    "campaign_id",
    "ad_id",
    "stat_datetime",
]

# ── 本地推报表配置 (v3.0 local/report/promotion/get/) ───────────
LOCAL_PROMOTION_METRICS = [
    "stat_cost",           # 消耗
    "show_cnt",            # 展示量
    "click_cnt",           # 点击量
    "ctr",                 # 点击率
    "cpm_platform",        # CPM
    "cpc_platform",        # CPC
    "convert_cnt",         # 转化数
    "conversion_cost",     # 转化成本
    "conversion_rate",     # 转化率
    "dy_follow",           # 抖音关注
    "dy_likes",            # 抖音点赞
    "dy_comment",          # 抖音评论
    "dy_share",            # 抖音分享
    "live_watch_one_minute_cnt",  # 直播间观看1分钟
    "dy_home_visited",     # 抖音主页访问
    "form",                # 表单提交
]

LOCAL_PROMOTION_DIMENSIONS = [
    "stat_datetime",       # 日期
    "promotion_id",        # 投放计划ID
    "promotion_name",      # 投放计划名称
    "promotion_status",    # 投放状态
    "local_life_shop_name",# 门店名称
    "local_life_shop_id",  # 门店ID
    "campaign_id",         # 广告组ID
    "campaign_name",       # 广告组名称
]

# ── Anomaly Detection ─────────────────────────────────────────
ANOMALY_THRESHOLD_PCT = 30       # 波动超过30%视为异常
ANOMALY_MIN_COST = 100           # 最小消耗阈值 (低于此值不告警)
ANOMALY_LOOKBACK_DAYS = 7        # 异常检测回溯天数

# ── Optimization Rules ────────────────────────────────────────
OPT_RULES = {
    "low_roi_pause": {
        "condition": "cost > 500 AND roi < 0.8",
        "action": "suggest_pause",
        "reason": "消耗大于500元但ROI低于0.8，建议暂停",
    },
    "high_roi_scale": {
        "condition": "roi > 2.0 AND cost < budget * 0.8",
        "action": "suggest_increase_budget",
        "reason": "ROI优秀且预算未跑满，建议加预算放量",
    },
    "high_cpa_warning": {
        "condition": "cpa > target_cpa * 1.5",
        "action": "suggest_lower_bid",
        "reason": "转化成本超出目标1.5倍，建议降低出价",
    },
    "low_ctr_creative": {
        "condition": "ctr < 1.0 AND show_cnt > 10000",
        "action": "suggest_replace_creative",
        "reason": "曝光过万但点击率低于1%，建议更换素材",
    },
}

# ── BP & Sub-Account Configuration ───────────────────────────
BP_ACCOUNT_ID = "1858351921937411"
BP_ACCOUNT_NAME = "三老板投流监测"

LOCAL_SUB_ACCOUNTS: dict[str, str] = {
    "01成都三老板代理户zx":   "1839326360573324",
    "02重庆大爷代理户_新zx":  "1865594502878474",
    "10昆明代理户_新zy":      "1865055776062746",
    "18南充三老板代理户zy":   "1863519436055834",
    "02重庆三姐代理户sp":     "1852177308604423",
    "08厦门三老板官户":       "1853375106745356",
    "09广州三老板代理户zy":   "1864967696007427",
    "21沈阳三老板代理户sp":   "1848477416316425",
    "06济南三老板代理户zx":   "1840305240496457",
    "11深圳三老板代理户zy":   "1864967740128472",
    "13贵阳三老板代理户sp":   "1823842640759050",
    "19太原三老板代理户zx":   "1864967486076041",
    "14遂宁三老板代理户zx":   "1841578956769291",
    "01成都三妹代理户zx":     "1829338747785675",
    "20长沙三老板官户":       "1839239891520969",
    "16南宁三老板代理户zx":   "1830437597210059",
    "07兰州三老板官户":       "1847306937564164",
    "17泉州三老板代理户zx":   "1864967660402696",
    "05佛山三老板官户":       "1834623001176460",
    "15武汉三老板官户":       "1834103230467140",
    "三老板长春店":           "1869051615722569",
    "03东莞三老板官户":       "1832892731182091",
    "24全国贴膜号代理户zy":   "1865055731399946",
    "12南昌三老板代理户zy":   "1853536748286468",
    "06济南直播官方户":       "1830804912346183",
    "04杭州三老板代理户zy":   "1864788406514058",
    "22全国直播号三老板zy":   "1859989342857292",
    "23全国号投线索客资zy":   "1865055686746124",
}
LOCAL_SUB_ACCOUNT_IDS = list(LOCAL_SUB_ACCOUNTS.values())

# ── Scheduler ─────────────────────────────────────────────────
SCHEDULE_INTERVAL_MINUTES = 30  # 每30分钟拉取一次数据
SCHEDULE_INTERVAL_HOURS = 6  # 保留兼容，实际由 SCHEDULE_INTERVAL_MINUTES 控制

# ── Alert Channels ────────────────────────────────────────────
WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL", "")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")

# ── Dashboard ─────────────────────────────────────────────────
DASHBOARD_REFRESH_SECONDS = 300  # 仪表盘自动刷新间隔
