"""
Ocean Engine configuration settings.

Values loaded from .env file with fallback defaults.
"""

import os
from pathlib import Path

# ── Load .env file ───────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/config/ → src/ → project_root/
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# ── Project Paths ───────────────────────────────────────
PROJECT_ROOT = _PROJECT_ROOT
DATA_DIR = PROJECT_ROOT / "data"

# ── Ocean Engine OAuth / API ────────────────────────────
OCEAN_ENGINE_APP_ID = os.getenv("OCEAN_ENGINE_APP_ID", "")
OCEAN_ENGINE_SECRET = os.getenv("OCEAN_ENGINE_SECRET", "")
OCEAN_ENGINE_AUTH_URL = os.getenv(
    "OCEAN_ENGINE_AUTH_URL",
    "https://api.oceanengine.com/open_api/oauth2",
)
OCEAN_ENGINE_ADVERTISER_ID = os.getenv("OCEAN_ENGINE_ADVERTISER_ID", "")
OCEAN_ENGINE_LOCAL_ACCOUNT_ID = os.getenv("OCEAN_ENGINE_LOCAL_ACCOUNT_ID", "")
OCEAN_ENGINE_ACCESS_TOKEN = os.getenv("OCEAN_ENGINE_ACCESS_TOKEN", "")
OCEAN_ENGINE_REDIRECT_URI = os.getenv(
    "OCEAN_ENGINE_REDIRECT_URI",
    "https://www.example.com/callback",
)
OCEAN_ENGINE_AUTH_CODE = os.getenv("OCEAN_ENGINE_AUTH_CODE", "")

# Token refresh buffer (seconds before expiry)
TOKEN_REFRESH_BUFFER = 3600  # 1 hour

# ── BP & Sub-Account Configuration ─────────────────────
BP_ACCOUNT_ID = "1858351921937411"
BP_ACCOUNT_NAME = "三老板投流监测"

# All local ad sub-accounts under this BP (from OceanEngine backend)
# These are the actual local_account_id values for Open API v3.0 material reports
LOCAL_SUB_ACCOUNTS: dict[str, str] = {
    # name → local_account_id
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
    "三老板长春店":           "1869051615722569",   # 新建号，0消耗
    "03东莞三老板官户":       "1832892731182091",
    "24全国贴膜号代理户zy":   "1865055731399946",
    "12南昌三老板代理户zy":   "1853536748286468",
    "06济南直播官方户":       "1830804912346183",   # 0消耗
    "04杭州三老板代理户zy":   "1864788406514058",   # 修正: 原18647788406514058多了一位
    "22全国直播号三老板zy":   "1859989342857292",   # 补充遗漏
    "23全国号投线索客资zy":   "1865055686746124",   # 补充遗漏，0消耗
}

# Ordered list of account IDs (for iteration)
LOCAL_SUB_ACCOUNT_IDS = list(LOCAL_SUB_ACCOUNTS.values())
