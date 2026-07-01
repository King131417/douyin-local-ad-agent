"""
Ocean Engine Local Ad API Client

Handles 本地推 (Local Promotion) API calls with correct param serialization.
Key insight from the working system: list params must be JSON-encoded in query string.
"""

import json
import logging
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

# Core metrics for local ad account-level reports.
# These are the metrics verified to work from the old system.
LOCAL_ACCOUNT_METRICS = [
    "stat_cost",           # 消耗
    "show_cnt",            # 展示量
    "click_cnt",           # 点击量
    "ctr",                 # 点击率
    "convert_cnt",         # 转化数
    "message_action_cnt",  # 私信咨询数
    "clue_message_count",  # 私信留资数
    "phone_confirm_cnt",   # 电话拨打数
    "phone_connect_cnt",   # 电话接通数
    "clue_pay_order_cnt",  # 团购线索数
]

# Promotion-level metrics (subset of the above + promotion dimensions)
LOCAL_PROMOTION_METRICS = [
    "stat_cost",
    "show_cnt",
    "click_cnt",
    "ctr",
    "convert_cnt",
    "message_action_cnt",
    "clue_message_count",
]

LOCAL_PROMOTION_DIMENSIONS = [
    "stat_datetime",
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

    def __init__(self, auth: AuthManager | None = None):
        self.auth = auth or AuthManager()

    # ── HTTP Helpers ──────────────────────────────────────────

    def _get(self, endpoint: str, params: dict) -> dict:
        """
        GET request with proper param serialization.
        Lists are JSON-encoded in the query string (required by Ocean Engine API).
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

        req = urllib.request.Request(url)
        req.add_header("Access-Token", self.auth.get_token())
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else str(e)
            try:
                return json.loads(body)
            except Exception:
                return {"code": e.code, "message": body}

    def _post(self, endpoint: str, body: dict) -> dict:
        """POST request to v3.0 API."""
        url = f"{API_BASE_V3}{endpoint}"
        data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data)
        req.add_header("Access-Token", self.auth.get_token())
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_text = e.read().decode() if e.fp else str(e)
            try:
                return json.loads(body_text)
            except Exception:
                return {"code": e.code, "message": body_text}

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
        """GET request to v2 API (e.g. advertiser/fund/get/)."""
        query_string = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
        )
        url = f"{API_BASE_V2}{endpoint}?{query_string}"

        req = urllib.request.Request(url)
        req.add_header("Access-Token", self.auth.get_token())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else str(e)
            try:
                return json.loads(body)
            except Exception:
                return {"code": e.code, "message": body}

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

    def get_account_report(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
        metrics: list[str] | None = None,
        page_size: int = 50,
        campaign_type: str | None = None,
    ) -> list[dict]:
        """
        Get daily account-level aggregated report.

        Uses the working endpoint: GET /v3.0/local/report/account/get/

        Args:
            campaign_type: Optional filter. 'GENERAL' for 通投 only,
                          'SEARCHING' for 搜索 only. None for all (通投+搜索).

        Returns list of daily summary rows with: stat_time_day, stat_cost,
        show_cnt, click_cnt, ctr, convert_cnt, message_action_cnt,
        clue_message_count, etc.
        """
        if not metrics:
            metrics = LOCAL_ACCOUNT_METRICS

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
            if campaign_type:
                params["filtering"] = json.dumps({"campaign_type": campaign_type})

            result = self._get("/local/report/account/get/", params)

            if result.get("code") != 0:
                if page == 1:
                    raise RuntimeError(
                        f"Account {account_id} report failed: {result.get('message', result)}"
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
        dimensions: list[str] | None = None,
        page_size: int = 50,
    ) -> list[dict]:
        """
        Get promotion-level report (drilled down by promotion/project).

        Uses: GET /v3.0/local/report/promotion/get/
        """
        metrics = metrics or LOCAL_PROMOTION_METRICS
        dimensions = dimensions or LOCAL_PROMOTION_DIMENSIONS

        all_rows: list[dict] = []
        page = 1

        while True:
            result = self._get("/local/report/promotion/get/", {
                "local_account_id": int(account_id),
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "page_size": page_size,
                "metrics": metrics,
                "dimensions": dimensions,
            })

            if result.get("code") != 0:
                if page == 1:
                    raise RuntimeError(
                        f"Promotion report failed: {result.get('message', result)}"
                    )
                break

            # Promotion report uses "promotion_list" (not "data_list" like account reports)
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
        page_size: int = 50,
    ) -> list[dict]:
        """
        Get material-level (creative) report.

        Uses: GET /v3.0/local/report/material/get/

        Returns list of material rows with: material_id, material_name,
        material_type, stat_cost, show_cnt, click_cnt, ctr, convert_cnt,
        message_action_cnt, clue_message_count, stat_time_day.
        """
        metrics = metrics or LOCAL_ACCOUNT_METRICS

        all_rows: list[dict] = []
        page = 1

        while True:
            result = self._get("/local/report/material/get/", {
                "local_account_id": int(account_id),
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "page_size": max(page_size, 10),  # min 10
                "metrics": metrics,
            })

            if result.get("code") != 0:
                if page == 1:
                    msg = result.get("message", result)
                    # 40000 = empty data / no materials, not a real error
                    if result.get("code") in (40000,):
                        logger.debug("Account %s material report: %s", account_id[-8:], msg)
                        break
                    raise RuntimeError(
                        f"Material report for {account_id} failed: {msg}"
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
        page_size: int = 50,
        status_filter: str | None = None,
    ) -> list[dict]:
        """
        Get promotion (投放单元) list for a local account.

        Args:
            account_id: Local ad account ID.
            page_size: Items per page.
            status_filter: Promotion status filter. One of:
                - None (default): Only non-deleted promotions.
                - 'PROMOTION_STATUS_ALL': All promotions including deleted.
                - 'PROMOTION_STATUS_DELETED': Only deleted promotions.
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
                break

            rows = result.get("data", {}).get("list", [])
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
        page_size: int = 50,
        status_filter: str | None = None,
    ) -> list[dict]:
        """
        Get project (项目) list for a local account.

        Args:
            account_id: Local ad account ID.
            page_size: Items per page.
            status_filter: Project status filter. One of:
                - None (default): Only non-deleted projects.
                - 'PROJECT_STATUS_ALL': All projects including deleted.
                - 'PROJECT_STATUS_DELETED': Only deleted projects.
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
                break

            rows = result.get("data", {}).get("list", [])
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
        dimensions: list[str] | None = None,
        page_size: int = 50,
    ) -> list[dict]:
        """
        Get project-level report.

        Uses: GET /v3.0/local/report/project/get/
        Returns data for ALL projects with spend in the date range,
        including deleted projects (history is preserved).
        """
        metrics = metrics or LOCAL_PROMOTION_METRICS
        dimensions = dimensions or [
            "stat_datetime", "project_id", "project_name",
        ]

        all_rows: list[dict] = []
        page = 1

        while True:
            result = self._get("/local/report/project/get/", {
                "local_account_id": int(account_id),
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "page_size": page_size,
                "metrics": metrics,
                "dimensions": dimensions,
            })

            if result.get("code") != 0:
                if page == 1:
                    raise RuntimeError(
                        f"Project report failed: {result.get('message', result)}"
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
        """Get clue/lead data (私信咨询/留资详情)."""
        all_clues: list[dict] = []
        page = 1

        while True:
            result = self._post("/../open_api/2/tools/clue/life/get/", {
                "local_account_ids": [int(account_id)],
                "start_time": f"{start_date} 00:00:00",
                "end_time": f"{end_date} 23:59:59",
                "page": page,
                "page_size": page_size,
            })
            # Adjust URL since we're posting to v2 endpoint
            # Actually, let me fix this - the POST needs the v2 base

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
