"""
Ocean Engine Local Ad API Client

Handles 本地推 (Local Promotion) API calls with correct param serialization.
Key insight from the working system: list params must be JSON-encoded in query string.
"""

import json
import logging
import random
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from .auth import AuthManager
from config.settings import LOCAL_SUB_ACCOUNTS, LOCAL_SUB_ACCOUNT_IDS

logger = logging.getLogger(__name__)

# Verified working API base for local ad v3.0
API_BASE_V3 = "https://api.oceanengine.com/open_api/v3.0"
# Standard API base
API_BASE_V2 = "https://api.oceanengine.com/open_api"

# ─────────────────────────────────────────────────────────
# Metrics definitions for local ad reports
# ─────────────────────────────────────────────────────────
# All fields verified via API batch testing on 2026-07-03 against
# account/promotion/material report endpoints (01成都 1839326360573324).
# Fields prefixed with ❌ below were tested and confirmed NOT in the dataset.
#
# ❌ attribution_conversion_cost  — 所有级别均不支持
# ❌ attribution_clue_message_count — 仅素材级支持，账户/推广级不支持
# ❌ ad_click_cnt / ad_show_cnt / form_submit_cnt / poi_collection_cnt — 不存在
# ─────────────────────────────────────────────────────────

LOCAL_ACCOUNT_METRICS = [
    # 基础消耗与展示
    "stat_cost",            # 消耗(元)
    "show_cnt",             # 展示次数
    "click_cnt",            # 点击次数
    "ctr",                  # 点击率
    "cpc_platform",         # 点击均价
    "cpm_platform",         # 千次展示费用
    "convert_cnt",          # 转化数(行为时间)
    "conversion_cost",      # 转化成本(行为时间)
    "conversion_rate",      # 转化率(行为时间)
    # ── 行为时间 - 线索指标 ──
    "message_action_cnt",   # 私信咨询数
    "clue_message_count",   # 私信留资数
    "phone_confirm_cnt",    # 电话拨打
    "phone_connect_cnt",    # 电话接通
    "clue_pay_order_cnt",   # 团购线索
    "form_cnt",             # 表单提交
    # ── 行为时间 - 意向指标（新增 v1.5）──
    "intention_form_cnt",               # 意向表单
    "intention_phone_cnt",              # 意向话单
    "intention_message_clue_cnt",       # 意向咨询
    # ── 计费时间 - 转化指标（与后台UI对齐）──
    "attribution_convert_cnt",                  # 转化数(计费时间)
    "attribution_conversion_rate",              # 转化率(计费时间)
    "attribution_message_action_cnt",           # 私信咨询数(计费时间)
    # ── 计费时间 - 线索指标（新增 v1.5）──
    "attribution_form_cnt",                     # 表单提交(计费时间)
    "attribution_clue_pay_order_cnt",           # 团购线索(计费时间)
    "attribution_phone_confirm_cnt",            # 电话拨打(计费时间)
    "attribution_phone_connect_cnt",            # 电话接通(计费时间)
    # ── 计费时间 - 意向指标（新增 v1.5）──
    "attribution_intention_form_cnt",           # 意向表单(计费时间)
    "attribution_intention_phone_cnt",          # 意向话单(计费时间)
    "attribution_intention_message_clue_cnt",   # 意向咨询(计费时间)
    # ── 直播指标（新增 v1.5）──
    "luban_live_enter_cnt",             # 直播间观看
    "live_watch_one_minute_count",      # 直播间超1分钟停留
    "luban_live_comment_cnt",           # 直播间评论
    "luban_live_share_cnt",             # 直播间分享
    # ── 视频播放指标（新增 v1.5）──
    "play_duration_5s",                 # 5s播放
    "play_duration_5s_show_cnt_rate",   # 5s播放率
    "play_25_feed_break",               # 25%进度播放
    "play_50_feed_break",               # 50%进度播放
    "play_75_feed_break",               # 75%进度播放
    "dy_like_rate",                     # 点赞率
]

# Video quality metrics (subset used for material quality analysis)
LOCAL_VIDEO_METRICS = [
    "total_play",               # 视频播放次数
    "play_duration_3s",         # 3s播放
    "play_duration_5s",         # 5s播放
    "play_duration_5s_show_cnt_rate",  # 5s播放率
    "play_25_feed_break",       # 25%进度
    "play_50_feed_break",       # 50%进度
    "play_75_feed_break",       # 75%进度
    "play_over",                # 完播次数
    "play_over_rate",           # 完播率
    "dy_like",                  # 点赞
    "dy_like_rate",             # 点赞率
    "dy_comment",               # 评论
    "dy_share",                 # 分享
    "dy_collect",               # 收藏
    "dy_follow",                # 新增粉丝
    "dy_home_visited",          # 主页访问
    "poi_recommend_count",      # 浏览商户人数
]

# Promotion-level metrics (same dataset as account-level)
LOCAL_PROMOTION_METRICS = [
    "stat_cost", "show_cnt", "click_cnt", "ctr",
    "cpc_platform", "cpm_platform",
    "convert_cnt", "conversion_cost", "conversion_rate",
    # 行为时间 - 线索
    "message_action_cnt", "clue_message_count",
    # 行为时间 - 意向
    "intention_form_cnt", "intention_phone_cnt", "intention_message_clue_cnt",
    # 计费时间 - 转化
    "attribution_convert_cnt", "attribution_conversion_rate",
    "attribution_message_action_cnt",
    # 计费时间 - 线索
    "attribution_form_cnt", "attribution_clue_pay_order_cnt",
    "attribution_phone_confirm_cnt", "attribution_phone_connect_cnt",
    # 计费时间 - 意向
    "attribution_intention_form_cnt",
    "attribution_intention_phone_cnt",
    "attribution_intention_message_clue_cnt",
    # 直播
    "luban_live_enter_cnt", "live_watch_one_minute_count",
    "luban_live_comment_cnt", "luban_live_share_cnt",
    # 视频播放
    "play_duration_5s", "play_duration_5s_show_cnt_rate",
    "play_25_feed_break", "play_50_feed_break", "play_75_feed_break",
    "dy_like_rate",
]

LOCAL_PROMOTION_DIMENSIONS = [
    "stat_time_day",
    "promotion_id",
    "promotion_name",
    "promotion_status",
    "local_life_shop_name",
    "local_life_shop_id",
    "project_id",
    "project_name",
]


class OceanEngineClient:
    """API client for Ocean Engine 本地推 (Local Promotion) v3.0 APIs."""

    # Retry configuration
    MAX_RETRIES: int = 3
    RETRY_BASE_DELAY: float = 1.0   # seconds, exponential: base * 2^attempt
    RETRY_MAX_DELAY: float = 30.0    # cap at 30 seconds
    RETRYABLE_HTTP_CODES: frozenset = frozenset({429, 500, 502, 503, 504})

    def __init__(self, auth: AuthManager | None = None):
        self.auth = auth or AuthManager()

    # ── HTTP Helpers ──────────────────────────────────────────

    def _get(self, endpoint: str, params: dict) -> dict:
        """
        GET request with proper param serialization.
        Lists are JSON-encoded in the query string (required by Ocean Engine API).
        Includes exponential backoff retry for transient errors (429, 5xx, network).
        """
        query_parts = []
        for k, v in params.items():
            if v is None:
                continue
            if isinstance(v, list):
                query_parts.append(f"{k}={urllib.parse.quote(json.dumps(v))}")
            elif isinstance(v, bool):
                query_parts.append(f"{k}={urllib.parse.quote(str(v).lower())}")
            else:
                query_parts.append(f"{k}={urllib.parse.quote(str(v))}")

        url = f"{API_BASE_V3}{endpoint}?{'&'.join(query_parts)}"

        last_exception = None
        for attempt in range(self.MAX_RETRIES):
            try:
                req = urllib.request.Request(url)
                req.add_header("Access-Token", self.auth.get_token())
                req.add_header("Content-Type", "application/json")

                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            except urllib.error.HTTPError as e:
                # Parse body for API-level errors
                body = e.read().decode() if e.fp else str(e)
                try:
                    result = json.loads(body)
                except Exception:
                    result = {"code": e.code, "message": body}

                # Retry on rate-limit or server errors
                if e.code in self.RETRYABLE_HTTP_CODES and attempt < self.MAX_RETRIES - 1:
                    wait = min(self.RETRY_BASE_DELAY * (2 ** attempt), self.RETRY_MAX_DELAY)
                    wait += random.uniform(0, 1)  # jitter
                    logger.debug("GET %s → HTTP %d, retry in %.1fs (attempt %d/%d)",
                                 endpoint, e.code, wait, attempt + 1, self.MAX_RETRIES)
                    time.sleep(wait)
                    last_exception = e
                    continue
                return result

            except (urllib.error.URLError, OSError, TimeoutError) as e:
                last_exception = e
                if attempt < self.MAX_RETRIES - 1:
                    wait = min(self.RETRY_BASE_DELAY * (2 ** attempt), self.RETRY_MAX_DELAY)
                    wait += random.uniform(0, 1)
                    logger.debug("GET %s → network error, retry in %.1fs (attempt %d/%d): %s",
                                 endpoint, wait, attempt + 1, self.MAX_RETRIES, e)
                    time.sleep(wait)
                    continue
                # Final attempt failed — return error dict
                return {"code": -1, "message": str(e)}

        # Should not reach here, but in case
        return {"code": -1, "message": str(last_exception)}

    def _post(self, endpoint: str, body: dict) -> dict:
        """POST request to v3.0 API with retry support."""
        url = f"{API_BASE_V3}{endpoint}"
        data = json.dumps(body).encode("utf-8")

        last_exception = None
        for attempt in range(self.MAX_RETRIES):
            try:
                req = urllib.request.Request(url, data=data)
                req.add_header("Access-Token", self.auth.get_token())
                req.add_header("Content-Type", "application/json")

                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            except urllib.error.HTTPError as e:
                body_text = e.read().decode() if e.fp else str(e)
                try:
                    result = json.loads(body_text)
                except Exception:
                    result = {"code": e.code, "message": body_text}

                if e.code in self.RETRYABLE_HTTP_CODES and attempt < self.MAX_RETRIES - 1:
                    wait = min(self.RETRY_BASE_DELAY * (2 ** attempt), self.RETRY_MAX_DELAY)
                    wait += random.uniform(0, 1)
                    logger.debug("POST %s → HTTP %d, retry in %.1fs (attempt %d/%d)",
                                 endpoint, e.code, wait, attempt + 1, self.MAX_RETRIES)
                    time.sleep(wait)
                    last_exception = e
                    continue
                return result

            except (urllib.error.URLError, OSError, TimeoutError) as e:
                last_exception = e
                if attempt < self.MAX_RETRIES - 1:
                    wait = min(self.RETRY_BASE_DELAY * (2 ** attempt), self.RETRY_MAX_DELAY)
                    wait += random.uniform(0, 1)
                    logger.debug("POST %s → network error, retry in %.1fs (attempt %d/%d): %s",
                                 endpoint, wait, attempt + 1, self.MAX_RETRIES, e)
                    time.sleep(wait)
                    continue
                return {"code": -1, "message": str(e)}

        return {"code": -1, "message": str(last_exception)}

    # ── Account Discovery ─────────────────────────────────────

    def discover_valid_accounts(
        self,
        candidate_ids: list[str] | None = None,
    ) -> dict[str, str]:
        """
        Discover valid local ad accounts.

        Priority:
        1. If candidate_ids provided, validate those
        2. Otherwise, return all configured sub-accounts (LOCAL_SUB_ACCOUNTS)
           These are pre-configured local_account_id values that work with Open API.

        Returns:
            {account_id: account_name} dict of valid accounts.
        """
        if candidate_ids is None:
            # Use statically configured sub-account IDs
            # These are the real local_account_id for Open API v3.0 material reports
            logger.info("Using %d configured sub-accounts from LOCAL_SUB_ACCOUNTS", len(LOCAL_SUB_ACCOUNTS))
            # Invert: config has {name: id}, we need {id: name}
            return {aid: name for name, aid in LOCAL_SUB_ACCOUNTS.items()}

        if not candidate_ids:
            logger.warning("No candidate account IDs available")
            return {}

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        valid: dict[str, str] = {}

        logger.info("Discovering valid accounts from %d candidates...", len(candidate_ids))
        for aid in candidate_ids:
            try:
                result = self._get("/local/report/account/get/", {
                    "local_account_id": int(aid),
                    "start_date": yesterday,
                    "end_date": yesterday,
                    "page": 1,
                    "page_size": 1,
                    "metrics": ["stat_cost"],
                })
                if result.get("code") == 0:
                    # Try to get account name from OAuth info
                    name = self._get_account_name(aid)
                    valid[str(aid)] = name
                    logger.debug("  ✅ %s (%s)", aid, name)
                else:
                    logger.debug("  ❌ %s: %s", aid, result.get("message", "unknown")[:50])
            except Exception as e:
                logger.debug("  ❌ %s: %s", aid, e)

        logger.info("Valid accounts: %d / %d candidates", len(valid), len(candidate_ids))
        return valid

    def _get_v2(self, endpoint: str, params: dict) -> dict:
        """GET request to v2 API (e.g. advertiser/fund/get/) with retry support."""
        query_string = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
        )
        url = f"{API_BASE_V2}{endpoint}?{query_string}"

        last_exception = None
        for attempt in range(self.MAX_RETRIES):
            try:
                req = urllib.request.Request(url)
                req.add_header("Access-Token", self.auth.get_token())
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode() if e.fp else str(e)
                try:
                    result = json.loads(body)
                except Exception:
                    result = {"code": e.code, "message": body}
                if e.code in self.RETRYABLE_HTTP_CODES and attempt < self.MAX_RETRIES - 1:
                    wait = min(self.RETRY_BASE_DELAY * (2 ** attempt), self.RETRY_MAX_DELAY)
                    wait += random.uniform(0, 1)
                    time.sleep(wait)
                    last_exception = e
                    continue
                return result
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                last_exception = e
                if attempt < self.MAX_RETRIES - 1:
                    wait = min(self.RETRY_BASE_DELAY * (2 ** attempt), self.RETRY_MAX_DELAY)
                    wait += random.uniform(0, 1)
                    time.sleep(wait)
                    continue
                return {"code": -1, "message": str(e)}
        return {"code": -1, "message": str(last_exception)}

    def _get_account_name(self, account_id: str) -> str:
        """Get account name via v2 advertiser/fund/get/ API.
        Falls back to LOCAL_SUB_ACCOUNTS reverse lookup. Returns '' if all fail."""
        # 1. Try API
        try:
            result = self._get_v2("/2/advertiser/fund/get/", {
                "advertiser_id": int(account_id),
            })
            if result.get("code") == 0:
                name = result.get("data", {}).get("name", "")
                if name and not name.startswith("account_"):
                    return name
        except Exception:
            pass
        # 2. Fallback: LOCAL_SUB_ACCOUNTS reverse lookup
        for acct_name, id_val in LOCAL_SUB_ACCOUNTS.items():
            if id_val == account_id:
                return acct_name
        # 3. All failed — return empty (don't use account_XXXX)
        return ""

    def fetch_all_account_names(
        self, account_ids: list[str]
    ) -> dict[str, str]:
        """
        Batch fetch real account names via v2 advertiser/fund/get/ API.

        Returns:
            {account_id: account_name} mapping.
        """
        names: dict[str, str] = {}
        logger.info("Fetching names for %d accounts...", len(account_ids))
        for i, aid in enumerate(account_ids):
            try:
                name = self._get_account_name(aid)
                names[aid] = name
                if i < 3 or i % 10 == 0:
                    logger.debug("  [%d/%d] %s → %s", i + 1, len(account_ids), aid[-8:], name)
            except Exception as e:
                names[aid] = ""  # _get_account_name already tried LOCAL_SUB_ACCOUNTS
                logger.debug("  [%d/%d] %s: failed (%s)", i + 1, len(account_ids), aid[-8:], e)
        logger.info("Fetched %d account names", len(names))
        return names

    # ── Account-Level Report ──────────────────────────────────

    def _build_report_filtering(
        self,
        campaign_type: str | None = None,
        marketing_goal: str | None = None,
        local_delivery_scene: str | None = None,
        delivery_mode: str | None = None,
        external_action: str | None = None,
        **extra,
    ) -> str | None:
        """Build filtering JSON for report APIs.

        Args:
            campaign_type: 'GENERAL' (通投) | 'SEARCHING' (搜索)
            marketing_goal: 'LIVE' (直播) | 'VIDEO_IMAGE' (短视频/图文)
            local_delivery_scene: 投放场景
            delivery_mode: 'AUTO' (自动投放) | 'MANUAL' (手动投放)
            external_action: 优化目标
        """
        parts: dict = {k: v for k, v in extra.items() if v is not None}
        if campaign_type is not None:
            parts["campaign_type"] = campaign_type
        if marketing_goal is not None:
            parts["marketing_goal"] = marketing_goal
        if local_delivery_scene is not None:
            parts["local_delivery_scene"] = local_delivery_scene
        if delivery_mode is not None:
            parts["delivery_mode"] = delivery_mode
        if external_action is not None:
            parts["external_action"] = external_action
        return json.dumps(parts) if parts else None

    def get_account_report(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
        metrics: list[str] | None = None,
        page_size: int = 100,
        time_granularity: str | None = None,
        campaign_type: str | None = None,
        marketing_goal: str | None = None,
        local_delivery_scene: str | None = None,
        delivery_mode: str | None = None,
        external_action: str | None = None,
    ) -> list[dict]:
        """
        Get daily account-level aggregated report.

        Uses: GET /v3.0/local/report/account/get/

        Args:
            campaign_type: 'GENERAL' for 通投, 'SEARCHING' for 搜索. None=全部.
                ⚠️ 必须放在filtering内（顶层传参会被API忽略，文档bug）。
            marketing_goal: 'LIVE' 直播 | 'VIDEO_IMAGE' 短视频/图文
            local_delivery_scene: 投放场景细分
            delivery_mode: 'AUTO' 自动投放 | 'MANUAL' 手动投放
            external_action: 优化目标
            time_granularity: 'TIME_GRANULARITY_DAILY' (默认)
                              'TIME_GRANULARITY_HOURLY' (≤7天)
                              'TIME_GRANULARITY_TOTAL' (汇总)

        Returns list of daily summary rows.
        """
        if not metrics:
            metrics = LOCAL_ACCOUNT_METRICS

        filtering = self._build_report_filtering(
            campaign_type=campaign_type,
            marketing_goal=marketing_goal,
            local_delivery_scene=local_delivery_scene,
            delivery_mode=delivery_mode,
            external_action=external_action,
        )

        all_rows: list[dict] = []
        page = 1

        while True:
            params: dict = {
                "local_account_id": int(account_id),
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "page_size": page_size,
                "metrics": metrics,
            }
            if time_granularity:
                params["time_granularity"] = time_granularity
            if filtering:
                params["filtering"] = filtering

            result = self._get("/local/report/account/get/", params)

            if result.get("code") != 0:
                if page == 1:
                    raise RuntimeError(
                        f"Account {account_id} report failed: {result.get('message', result)}"
                    )
                # Non-page-1 error: warn and stop (partial data returned)
                logger.warning(
                    "Account %s report page=%d failed: %s (partial data: %d rows)",
                    account_id[-8:], page, result.get("message", ""), len(all_rows),
                )
                break

            rows = result.get("data", {}).get("data_list", [])
            if not rows:
                break

            all_rows.extend(rows)
            page += 1

            if len(rows) < page_size:
                break

        return all_rows

    def get_account_report_date_range(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
        metrics: list[str] | None = None,
        max_days_per_batch: int = 30,
        campaign_type: str | None = None,
        time_granularity: str | None = None,
    ) -> list[dict]:
        """Get account reports for a wide date range, auto-batching."""
        all_rows: list[dict] = []
        current = start_date
        while current <= end_date:
            batch_end = min(current + timedelta(days=max_days_per_batch - 1), end_date)
            rows = self.get_account_report(
                account_id,
                current.strftime("%Y-%m-%d"),
                batch_end.strftime("%Y-%m-%d"),
                metrics=metrics,
                campaign_type=campaign_type,
                time_granularity=time_granularity,
            )
            all_rows.extend(rows)
            current = batch_end + timedelta(days=1)
        return all_rows

    # ── Promotion-Level Report ────────────────────────────────

    def get_promotion_report(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
        metrics: list[str] | None = None,
        page_size: int = 100,
        time_granularity: str | None = None,
        campaign_type: str | None = None,
        marketing_goal: str | None = None,
        local_delivery_scene: str | None = None,
    ) -> list[dict]:
        """
        Get promotion-level report (drilled down by promotion/project).

        Uses: GET /v3.0/local/report/promotion/get/

        Args:
            campaign_type: 'GENERAL' (通投) | 'SEARCHING' (搜索) | None (全部)
            marketing_goal: 'LIVE' (直播) | 'VIDEO_IMAGE' (短视频/图文)

        Note: dimensions (promotion_id, project_id, stat_time_day, etc.)
        are automatically returned by the API — no "dimensions" param needed.
        """
        metrics = metrics or LOCAL_PROMOTION_METRICS

        filtering = self._build_report_filtering(
            campaign_type=campaign_type,
            marketing_goal=marketing_goal,
            local_delivery_scene=local_delivery_scene,
        )

        all_rows: list[dict] = []
        page = 1

        while True:
            params: dict = {
                "local_account_id": int(account_id),
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "page_size": page_size,
                "metrics": metrics,
            }
            if time_granularity:
                params["time_granularity"] = time_granularity
            if filtering:
                params["filtering"] = filtering

            result = self._get("/local/report/promotion/get/", params)

            if result.get("code") != 0:
                if page == 1:
                    raise RuntimeError(
                        f"Promotion report failed: {result.get('message', result)}"
                    )
                logger.warning(
                    "Promotion report page=%d failed: %s (partial: %d rows)",
                    page, result.get("message", ""), len(all_rows),
                )
                break

            # Promotion report uses "promotion_list" (not "data_list")
            rows = result.get("data", {}).get("promotion_list", [])
            if not rows:
                break

            all_rows.extend(rows)
            page += 1

            if len(rows) < page_size:
                break

        return all_rows

    # ── Material-Level Report ─────────────────────────────────

    def get_material_report(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
        metrics: list[str] | None = None,
        page_size: int = 100,
        time_granularity: str | None = None,
        campaign_type: str | None = None,
        marketing_goal: str | None = None,
        local_delivery_scene: str | None = None,
        delivery_mode: str | None = None,
        external_action: str | None = None,
        promotion_ids: list[str] | None = None,
        material_ids: list[str] | None = None,
        material_type: str | None = None,
    ) -> list[dict]:
        """
        Get material-level (creative) report.

        Uses: GET /v3.0/local/report/material/get/

        Args:
            campaign_type: 'GENERAL' (通投) | 'SEARCHING' (搜索) | None (全部)
            marketing_goal: 'LIVE' (直播) | 'VIDEO_IMAGE' (短视频/图文)
            local_delivery_scene: 投放场景
            delivery_mode: 'AUTO' (自动投放) | 'MANUAL' (手动投放)
            external_action: 优化目标
            promotion_ids: Optional list of promotion IDs to filter by.
                Enables material→promotion linkage (SDK v1.34.1).
            material_ids: Optional list of material IDs to filter by.
            material_type: 素材类型过滤
            time_granularity: 'TIME_GRANULARITY_DAILY'/'HOURLY'/'TOTAL'
        """
        metrics = metrics or LOCAL_ACCOUNT_METRICS

        filtering = self._build_report_filtering(
            campaign_type=campaign_type,
            marketing_goal=marketing_goal,
            local_delivery_scene=local_delivery_scene,
            delivery_mode=delivery_mode,
            external_action=external_action,
            promotion_ids=([int(pid) for pid in promotion_ids] if promotion_ids else None),
            material_ids=([int(mid) for mid in material_ids] if material_ids else None),
            material_type=material_type,
        )

        all_rows: list[dict] = []
        page = 1

        while True:
            params: dict = {
                "local_account_id": int(account_id),
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "page_size": max(page_size, 10),  # min 10
                "metrics": metrics,
            }
            if time_granularity:
                params["time_granularity"] = time_granularity
            if filtering:
                params["filtering"] = filtering

            result = self._get("/local/report/material/get/", params)

            if result.get("code") != 0:
                if page == 1:
                    msg = result.get("message", result)
                    if result.get("code") in (40000,):
                        logger.debug("Account %s material report: %s", account_id[-8:], msg)
                        break
                    raise RuntimeError(
                        f"Material report for {account_id} failed: {msg}"
                    )
                logger.warning(
                    "Material report page=%d failed: %s (partial: %d rows)",
                    page, result.get("message", ""), len(all_rows),
                )
                break

            rows = result.get("data", {}).get("material_list", [])
            if not rows:
                break

            all_rows.extend(rows)
            page += 1

            page_info = result.get("data", {}).get("page_info", {})
            if page > page_info.get("total_page", 1):
                break

        return all_rows

    def sync_all_materials(
        self,
        account_ids: list[str],
        start_date: str,
        end_date: str,
        on_account: Optional[Callable] = None,
    ) -> dict[str, list[dict]]:
        """
        Sync material reports for multiple accounts.
        on_account(account_id, rows) is called for each account's results.
        """
        results: dict[str, list[dict]] = {}
        total = len(account_ids)

        for i, aid in enumerate(account_ids):
            try:
                rows = self.get_material_report(aid, start_date, end_date)
                results[aid] = rows
                logger.info("[%d/%d] %s: %d materials", i + 1, total, aid[-8:], len(rows))
                if on_account:
                    on_account(aid, rows)
            except Exception as e:
                logger.warning("[%d/%d] %s: MATERIAL SKIP (%s)", i + 1, total, aid[-8:], e)

        return results

    # ── Multi-Account Sync ────────────────────────────────────

    def sync_all_accounts(
        self,
        account_ids: list[str],
        start_date: str,
        end_date: str,
        on_account: Optional[Callable] = None,
    ) -> dict[str, list[dict]]:
        """
        Sync reports for multiple accounts in parallel.
        on_account(account_id, rows) is called for each account.
        """
        results: dict[str, list[dict]] = {}
        total = len(account_ids)

        for i, aid in enumerate(account_ids):
            try:
                rows = self.get_account_report(aid, start_date, end_date)
                results[aid] = rows
                logger.info("[%d/%d] %s: %d rows", i + 1, total, aid[-8:], len(rows))
                if on_account:
                    on_account(aid, rows)
            except Exception as e:
                logger.warning("[%d/%d] %s: SKIPPED (%s)", i + 1, total, aid[-8:], e)

        return results

    # ── Promotion List ────────────────────────────────────────

    def get_promotion_list(
        self,
        account_id: str,
        page_size: int = 100,
        status_filter: str | None = None,
    ) -> list[dict]:
        """
        Get promotion (投放单元) list for a local account.
        """
        all_items: list[dict] = []
        page = 1

        while True:
            params: dict = {
                "local_account_id": int(account_id),
                "page": page,
                "page_size": page_size,
            }
            if status_filter:
                params["filtering"] = json.dumps(
                    {"promotion_status_first": status_filter}
                )

            result = self._get("/local/promotion/list/", params)

            if result.get("code") != 0:
                if page == 1:
                    raise RuntimeError(
                        f"Promotion list failed: {result.get('message', result)}"
                    )
                logger.warning(
                    "Promotion list page=%d failed: %s", page, result.get("message", ""),
                )
                break

            rows = result.get("data", {}).get("promotion_list", [])
            if not rows:
                break

            all_items.extend(rows)
            page += 1
            if len(rows) < page_size:
                break

        return all_items

    # ── Project List ───────────────────────────────────────────

    def get_project_list(
        self,
        account_id: str,
        page_size: int = 100,
        status_filter: str | None = None,
    ) -> list[dict]:
        """
        Get project (项目) list for a local account.
        """
        all_items: list[dict] = []
        page = 1

        while True:
            params: dict = {
                "local_account_id": int(account_id),
                "page": page,
                "page_size": page_size,
            }
            if status_filter:
                params["filtering"] = json.dumps(
                    {"project_status_first": status_filter}
                )

            result = self._get("/local/project/list/", params)

            if result.get("code") != 0:
                if page == 1:
                    raise RuntimeError(
                        f"Project list failed: {result.get('message', result)}"
                    )
                logger.warning(
                    "Project list page=%d failed: %s", page, result.get("message", ""),
                )
                break

            rows = result.get("data", {}).get("project_list", [])
            if not rows:
                break

            all_items.extend(rows)
            page += 1
            if len(rows) < page_size:
                break

        return all_items

    # ── Project-Level Report ───────────────────────────────────

    def get_project_report(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
        metrics: list[str] | None = None,
        page_size: int = 100,
        time_granularity: str | None = None,
        campaign_type: str | None = None,
        marketing_goal: str | None = None,
        local_delivery_scene: str | None = None,
    ) -> list[dict]:
        """
        Get project-level report.

        Uses: GET /v3.0/local/report/project/get/

        Args:
            campaign_type: 'GENERAL' (通投) | 'SEARCHING' (搜索) | None (全部)

        Returns data for ALL projects with spend in the date range,
        including deleted projects (history is preserved).

        Note: dimensions (project_id, project_name, stat_time_day, etc.)
        are automatically returned by the API — no "dimensions" param needed.
        """
        metrics = metrics or LOCAL_PROMOTION_METRICS

        filtering = self._build_report_filtering(
            campaign_type=campaign_type,
            marketing_goal=marketing_goal,
            local_delivery_scene=local_delivery_scene,
        )

        all_rows: list[dict] = []
        page = 1

        while True:
            params: dict = {
                "local_account_id": int(account_id),
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "page_size": page_size,
                "metrics": metrics,
            }
            if time_granularity:
                params["time_granularity"] = time_granularity
            if filtering:
                params["filtering"] = filtering

            result = self._get("/local/report/project/get/", params)

            if result.get("code") != 0:
                if page == 1:
                    raise RuntimeError(
                        f"Project report failed: {result.get('message', result)}"
                    )
                logger.warning(
                    "Project report page=%d failed: %s (partial: %d rows)",
                    page, result.get("message", ""), len(all_rows),
                )
                break

            # Project report uses "project_list" key
            rows = result.get("data", {}).get("project_list", [])
            if not rows:
                break

            all_rows.extend(rows)
            page += 1

            if len(rows) < page_size:
                break

        return all_rows

    # ── Reconciliation ─────────────────────────────────────────

    def reconcile_deleted_entities(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
    ) -> dict:
        """
        Reconcile account total vs promotion-level sum to detect gaps
        caused by deleted promotions/projects.

        Returns:
            {
                "account_total": float,
                "promotion_total": float,
                "gap": float,
                "gap_pct": float,
                "deleted_promotion_ids": [...],
                "deleted_project_ids": [...],
            }
        """
        result: dict = {
            "account_total": 0.0,
            "promotion_total": 0.0,
            "gap": 0.0,
            "gap_pct": 0.0,
            "deleted_promotion_ids": [],
            "deleted_project_ids": [],
        }

        # 1. Get account-level total
        acc_rows = self.get_account_report(
            account_id, start_date, end_date, page_size=100,
        )
        result["account_total"] = sum(
            r.get("stat_cost", 0) for r in acc_rows
        )

        # 2. Get promotion-level total (already includes deleted entities with spend)
        promo_rows = self.get_promotion_report(
            account_id, start_date, end_date, page_size=100,
        )
        result["promotion_total"] = sum(
            r.get("stat_cost", 0) for r in promo_rows
        )

        # 3. Calculate gap
        result["gap"] = result["account_total"] - result["promotion_total"]
        if result["account_total"] > 0:
            result["gap_pct"] = result["gap"] / result["account_total"] * 100

        # 4. If gap exists, check deleted promotions/projects
        if abs(result["gap_pct"]) > 0.1:
            # Fetch deleted promotions
            try:
                del_promos = self.get_promotion_list(
                    account_id,
                    status_filter="PROMOTION_STATUS_DELETED",
                )
                result["deleted_promotion_ids"] = [
                    p["promotion_id"] for p in del_promos
                ]
            except Exception:
                pass

            # Fetch deleted projects
            try:
                del_projects = self.get_project_list(
                    account_id,
                    status_filter="PROJECT_STATUS_DELETED",
                )
                result["deleted_project_ids"] = [
                    p["project_id"] for p in del_projects
                ]
            except Exception:
                pass

        return result

    # ── Clue Data ─────────────────────────────────────────────

    def get_clue_data(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
        page_size: int = 100,
    ) -> list[dict]:
        """Get clue/lead data (私信咨询/留资详情).

        Uses POST /v2/tools/clue/life/get/ — local ad clue list API.
        """
        all_clues: list[dict] = []
        page = 1

        while True:
            url = f"{API_BASE_V2}/2/tools/clue/life/get/"
            data = json.dumps({
                "local_account_ids": [int(account_id)],
                "start_time": f"{start_date} 00:00:00",
                "end_time": f"{end_date} 23:59:59",
                "page": page,
                "page_size": page_size,
            }).encode("utf-8")

            req = urllib.request.Request(url, data=data)
            req.add_header("Access-Token", self.auth.get_token())
            req.add_header("Content-Type", "application/json")

            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode() if e.fp else str(e)
                try:
                    result = json.loads(body)
                except Exception:
                    result = {"code": e.code, "message": body}

            if result.get("code") != 0:
                if page == 1:
                    logger.warning("Clue API failed: %s", result.get("message"))
                break

            clues = result.get("data", {}).get("list", [])
            if not clues:
                break
            all_clues.extend(clues)

            page_info = result.get("data", {}).get("page_info", {})
            if page >= page_info.get("page_total", 1):
                break
            page += 1

        return all_clues
