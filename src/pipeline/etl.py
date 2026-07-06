"""
ETL Pipeline — Multi-Account Local Ad Data Sync

Flow:
1. Discover valid accounts via API
2. For each account: pull daily reports from API
3. Transform and load into SQLite
"""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional

from src.api.client import OceanEngineClient
from .storage import Storage

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds, exponential: 2, 4, 8
INTER_ACCOUNT_DELAY = 0.5  # seconds between accounts


class ETLPipeline:
    """Orchestrates data extraction, transformation, and loading."""

    def __init__(
        self,
        client: Optional[OceanEngineClient] = None,
        storage: Optional[Storage] = None,
    ):
        self.client = client or OceanEngineClient()
        self.storage = storage or Storage()

    # ── Full Pipeline ──────────────────────────────────────────

    def run_daily_sync(
        self,
        target_date: Optional[date] = None,
        account_ids: Optional[list[str]] = None,
    ) -> dict:
        """
        Sync daily data for all valid accounts.

        Args:
            target_date: Which day to sync (default: yesterday)
            account_ids: Specific account IDs (default: discover from API)

        Returns:
            {account_id: row_count} summary.
        """
        target = target_date or (date.today() - timedelta(days=1))
        date_str = target.strftime("%Y-%m-%d")

        # Discover accounts if not provided
        if account_ids is None:
            logger.info("=== Discovering valid accounts ===")
            valid = self.client.discover_valid_accounts()
            account_ids = list(valid.keys())
            # Fallback: if API discovery returns too few, use database accounts
            if len(account_ids) < 2:
                db_ids = self.storage.get_account_ids()
                if db_ids:
                    logger.info("Fallback to %d accounts from database", len(db_ids))
                    account_ids = db_ids

        if not account_ids:
            logger.warning("No valid accounts found, nothing to sync")
            return {}

        logger.info("=== Daily Sync: %s, %d accounts ===", date_str, len(account_ids))

        results = {}
        for aid in account_ids:
            try:
                # API 默认返回通投+搜索全量（按 SKILL.md 规范，不传 campaign_type）
                rows = self.client.get_account_report(aid, date_str, date_str)
                if rows:
                    self.storage.ensure_account(aid)
                    count = self.storage.upsert_account_reports(aid, rows, delivery_type="total")
                    results[aid] = count
                    logger.info("  %s: %d rows (total)", aid[-8:], count)
                else:
                    logger.info("  %s: no data", aid[-8:])
            except Exception as e:
                logger.warning("  %s: SKIPPED (%s)", aid[-8:], e)

        logger.info("=== Daily sync complete: %d/%d accounts ===", len(results), len(account_ids))

        # Sync promotion-level data first (material sync needs promotion list)
        promo_results = self._sync_promotions(date_str, account_ids)
        total_promos = sum(promo_results.values())
        logger.info("=== Promotion sync: %d promotions across %d accounts ===", total_promos, len(promo_results))

        # Sync material-level data (uses promotion info for attribution)
        material_results = self._sync_materials(date_str, account_ids)
        total_materials = sum(material_results.values())
        logger.info("=== Material sync: %d materials across %d accounts ===", total_materials, len(material_results))

        # Sync project-level data
        project_results = self._sync_projects(date_str, account_ids)
        total_projects = sum(project_results.values())
        logger.info("=== Project sync: %d projects across %d accounts ===", total_projects, len(project_results))

        # Refresh account names from API
        self.refresh_account_names(account_ids)

        return results

    def refresh_account_names(self, account_ids: list[str]):
        """Fetch and persist real account names from API.
        Only updates non-empty names — never overwrites with account_XXXX."""
        names = self.client.fetch_all_account_names(account_ids)
        updated = 0
        for aid, name in names.items():
            if name and not name.startswith("account_"):
                self.storage.ensure_account(aid, name=name)
                updated += 1
        logger.info("Refreshed names for %d/%d accounts (skipped %d empty)",
                     updated, len(names), len(names) - updated)

    def _sync_materials(
        self,
        date_str: str,
        account_ids: list[str],
    ) -> dict[str, int]:
        """
        Sync material-level data for all accounts on a given date.
        Uses per-promotion queries to capture project/promotion attribution.
        Falls back to bulk query if no promotions found.
        Returns {account_id: material_count}.
        """
        logger.info("=== Syncing material data for %s ===", date_str)
        results: dict[str, int] = {}

        for i, aid in enumerate(account_ids):
            try:
                count = self._sync_account_materials(aid, date_str, date_str)
                results[aid] = count
                if count > 0:
                    logger.debug("  [%d/%d] %s: %d materials", i + 1, len(account_ids), aid[-8:], count)
                else:
                    results[aid] = 0
            except Exception as e:
                logger.debug("  [%d/%d] %s: material skip (%s)", i + 1, len(account_ids), aid[-8:], e)
                results[aid] = 0

        logger.info("=== Material sync done: %d total materials ===", sum(results.values()))
        return results

    def _sync_account_materials(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
    ) -> int:
        """Sync materials for a single account with promotion/project attribution.

        Strategy:
        1. Get all active promotions for the account via API
        2. If API returns empty, fall back to promotion_reports table
        3. Query materials per-promotion (via promotion_ids filter)
        4. Inject promotion_id/name + project_id/name into each row
        5. Fall back to bulk query if no promotions at all
        """
        total_count = 0

        # Get promotions for this account (API first)
        try:
            promotions = self.client.get_promotion_list(account_id, page_size=100)
        except Exception as e:
            logger.debug("  Failed to get promotions for %s: %s, using fallback", account_id[-8:], e)
            promotions = []

        # Fallback: get promotions from already-synced promotion_reports table
        if not promotions:
            try:
                conn = self.storage._get_conn()
                rows = conn.execute(
                    """
                    SELECT DISTINCT promotion_id, promotion_name, project_id, project_name
                    FROM promotion_reports
                    WHERE account_id = ? AND stat_date BETWEEN ? AND ?
                      AND promotion_id != ''
                    """,
                    (account_id, start_date, end_date),
                ).fetchall()
                promotions = [
                    {
                        "promotion_id": r["promotion_id"],
                        "promotion_name": r["promotion_name"] or "",
                        "project_id": r["project_id"] or "",
                        "project_name": r["project_name"] or "",
                    }
                    for r in rows
                ]
                if promotions:
                    logger.debug(
                        "  %s: using %d promotions from DB fallback",
                        account_id[-8:], len(promotions),
                    )
            except Exception as e:
                logger.debug("  DB fallback for promotions failed: %s", e)
                promotions = []

        if promotions:
            # Per-promotion material sync with attribution
            promo_map = {p["promotion_id"]: p for p in promotions}
            seen_materials: set[str] = set()  # track (material_id, stat_date) to avoid dup upsert noise

            for promo in promotions:
                pid = promo.get("promotion_id")
                pname = promo.get("promotion_name", "")
                proj_id = promo.get("project_id", "")
                proj_name = promo.get("project_name", "")

                try:
                    rows = self.client.get_material_report(
                        account_id, start_date, end_date,
                        promotion_ids=[pid],
                    )
                    if not rows:
                        continue

                    # Inject attribution fields into each row
                    for r in rows:
                        r["promotion_id"] = str(pid) if pid else ""
                        r["promotion_name"] = str(pname) if pname else ""
                        r["project_id"] = str(proj_id) if proj_id else ""
                        r["project_name"] = str(proj_name) if proj_name else ""

                    count = self.storage.upsert_material_reports(account_id, rows)
                    total_count += count
                except Exception as e:
                    # Per-promotion failures are non-fatal; skip this promotion's materials
                    logger.debug(
                        "  Material query failed for promotion %s of %s: %s",
                        str(pid)[:8], account_id[-8:], e,
                    )
                    continue

            # Bulk fallback: also do one unfiltered pass to catch any materials
            # not covered by individual promotion queries (e.g. deleted promotions)
            #
            # IMPORTANT: If per-promotion queries returned 0 materials (all accounts
            # where API's promotion_ids filter is unsupported), inject attribution
            # from promotions. For single-promotion accounts, attribute all bulk
            # materials to that promotion. For multi-promotion accounts, the API
            # natively returns promotion_id/promotion_name/project_id but NOT
            # project_name — look it up from promotion_reports table.
            try:
                bulk_rows = self.client.get_material_report(account_id, start_date, end_date)
                if bulk_rows:
                    if total_count == 0 and len(promotions) == 1:
                        # Single-promotion account: promotion_ids filter returned 0;
                        # attribute all bulk materials to the only promotion.
                        p = promotions[0]
                        pid = p.get("promotion_id", "")
                        pname = p.get("promotion_name", "")
                        proj_id = p.get("project_id", "")
                        proj_name = p.get("project_name", "")
                        for r in bulk_rows:
                            r["promotion_id"] = str(pid)
                            r["promotion_name"] = str(pname)
                            r["project_id"] = str(proj_id)
                            r["project_name"] = str(proj_name)
                    elif total_count == 0 and len(promotions) > 1:
                        # Multi-promotion account with failed per-promo queries.
                        # The API natively returns promotion_id/promotion_name/project_id
                        # but NOT project_name. Build a lookup from promotion_reports
                        # (all dates for this account) to fill in project_name.
                        self._enrich_project_name(account_id, bulk_rows)

                    # Always enrich: even per-promotion path may have bulk rows
                    # with API-returned promotion_id but missing project_name
                    self._enrich_project_name(account_id, bulk_rows)

                    count = self.storage.upsert_material_reports(account_id, bulk_rows)
                    total_count += count
            except Exception as e:
                logger.debug("  Bulk material fallback for %s: %s", account_id[-8:], e)

        else:
            # No promotions — fall back to original bulk behavior
            rows = self.client.get_material_report(account_id, start_date, end_date)
            if rows:
                total_count = self.storage.upsert_material_reports(account_id, rows)

        return total_count

    def _enrich_project_name(self, account_id: str, rows: list[dict]) -> None:
        """Fill in missing project_name by looking up promotion_id/project_id
        in promotion_reports and project_reports tables (all dates).

        The material report API returns promotion_id, promotion_name, and
        project_id natively, but NEVER returns project_name. This method
        fills that gap by cross-referencing with other report tables.

        Modifies rows in-place.
        """
        # Collect promotion_ids and project_ids that need lookup
        promo_ids_need_lookup = set()
        proj_ids_need_lookup = set()
        for r in rows:
            proj_name = str(r.get("project_name", "") or "")
            if not proj_name:
                pid = str(r.get("promotion_id", "") or "")
                if pid:
                    promo_ids_need_lookup.add(pid)
                proj_id = str(r.get("project_id", "") or "")
                if proj_id:
                    proj_ids_need_lookup.add(proj_id)

        if not promo_ids_need_lookup and not proj_ids_need_lookup:
            return  # all rows already have project_name

        # Build lookup maps from DB (all dates for this account)
        conn = self.storage._get_conn()

        # Map: promotion_id -> project_name (from promotion_reports, any date)
        promo_to_proj_name: dict[str, str] = {}
        if promo_ids_need_lookup:
            placeholders = ",".join(["?"] * len(promo_ids_need_lookup))
            db_rows = conn.execute(
                f"""
                SELECT DISTINCT promotion_id, project_name
                FROM promotion_reports
                WHERE account_id = ? AND promotion_id IN ({placeholders})
                  AND project_name IS NOT NULL AND project_name != ''
                """,
                (account_id, *promo_ids_need_lookup),
            ).fetchall()
            for dr in db_rows:
                promo_to_proj_name[str(dr["promotion_id"])] = dr["project_name"]

        # Map: project_id -> project_name (from project_reports, any date)
        proj_id_to_name: dict[str, str] = {}
        if proj_ids_need_lookup:
            placeholders = ",".join(["?"] * len(proj_ids_need_lookup))
            db_rows = conn.execute(
                f"""
                SELECT DISTINCT project_id, project_name
                FROM project_reports
                WHERE account_id = ? AND project_id IN ({placeholders})
                  AND project_name IS NOT NULL AND project_name != ''
                """,
                (account_id, *proj_ids_need_lookup),
            ).fetchall()
            for dr in db_rows:
                proj_id_to_name[str(dr["project_id"])] = dr["project_name"]

        # Also check promotion_reports for project_id -> project_name
        if proj_ids_need_lookup:
            still_missing = proj_ids_need_lookup - set(proj_id_to_name.keys())
            if still_missing:
                placeholders = ",".join(["?"] * len(still_missing))
                db_rows = conn.execute(
                    f"""
                    SELECT DISTINCT project_id, project_name
                    FROM promotion_reports
                    WHERE account_id = ? AND project_id IN ({placeholders})
                      AND project_name IS NOT NULL AND project_name != ''
                    """,
                    (account_id, *still_missing),
                ).fetchall()
                for dr in db_rows:
                    proj_id_to_name[str(dr["project_id"])] = dr["project_name"]

        conn.close()

        if not promo_to_proj_name and not proj_id_to_name:
            return  # no lookup data available

        # Apply lookups to rows
        enriched = 0
        for r in rows:
            proj_name = str(r.get("project_name", "") or "")
            if proj_name:
                continue  # already has project_name

            # Try promotion_id -> project_name first
            pid = str(r.get("promotion_id", "") or "")
            if pid and pid in promo_to_proj_name:
                r["project_name"] = promo_to_proj_name[pid]
                enriched += 1
                continue

            # Try project_id -> project_name
            proj_id = str(r.get("project_id", "") or "")
            if proj_id and proj_id in proj_id_to_name:
                r["project_name"] = proj_id_to_name[proj_id]
                enriched += 1
                continue

            # Fallback: if promotion_name is available but project_name is not,
            # use promotion_name as project_name (for deleted/old promotions
            # where the project has been removed from the system)
            promo_name = str(r.get("promotion_name", "") or "")
            if promo_name and pid:
                r["project_name"] = promo_name
                enriched += 1

        if enriched:
            logger.debug(
                "  %s: enriched %d materials with project_name from DB lookup",
                account_id[-8:], enriched,
            )

    def _sync_promotions(
        self,
        date_str: str,
        account_ids: list[str],
    ) -> dict[str, int]:
        """
        Sync promotion-level data for all accounts on a given date.
        Returns {account_id: promotion_count}.
        """
        logger.info("=== Syncing promotion data for %s ===", date_str)
        results: dict[str, int] = {}

        for i, aid in enumerate(account_ids):
            try:
                rows = self.client.get_promotion_report(aid, date_str, date_str)
                if rows:
                    count = self.storage.upsert_promotion_reports(aid, rows)
                    results[aid] = count
                    logger.debug("  [%d/%d] %s: %d promotions", i + 1, len(account_ids), aid[-8:], count)
                else:
                    results[aid] = 0
            except Exception as e:
                logger.debug("  [%d/%d] %s: promotion skip (%s)", i + 1, len(account_ids), aid[-8:], e)
                results[aid] = 0

        logger.info("=== Promotion sync done: %d total promotions ===", sum(results.values()))
        return results

    def _sync_projects(
        self,
        date_str: str,
        account_ids: list[str],
    ) -> dict[str, int]:
        """
        Sync project-level data for all accounts on a given date.
        Returns {account_id: project_count}.
        """
        logger.info("=== Syncing project data for %s ===", date_str)
        results: dict[str, int] = {}

        for i, aid in enumerate(account_ids):
            try:
                rows = self.client.get_project_report(aid, date_str, date_str)
                if rows:
                    count = self.storage.upsert_project_reports(aid, rows)
                    results[aid] = count
                    logger.debug("  [%d/%d] %s: %d projects", i + 1, len(account_ids), aid[-8:], count)
                else:
                    results[aid] = 0
            except Exception as e:
                logger.debug("  [%d/%d] %s: project skip (%s)", i + 1, len(account_ids), aid[-8:], e)
                results[aid] = 0

        logger.info("=== Project sync done: %d total projects ===", sum(results.values()))
        return results

    def run_backfill(
        self,
        days: int = 30,
        account_ids: Optional[list[str]] = None,
    ) -> dict:
        """
        Backfill historical data for the past N days.
        Syncs account + material + promotion reports for full range.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
        return self.run_date_range(start_date, end_date, account_ids)

    def run_date_range(
        self,
        start_date: date,
        end_date: date,
        account_ids: Optional[list[str]] = None,
    ) -> dict:
        """
        Sync data for a date range across all accounts.
        Uses date-range APIs (not day-by-day) for efficiency.
        Syncs account + material + promotion reports for the full range.
        """
        if account_ids is None:
            valid = self.client.discover_valid_accounts()
            account_ids = list(valid.keys())
            if len(account_ids) < 2:
                db_ids = self.storage.get_account_ids()
                if db_ids:
                    account_ids = db_ids

        if not account_ids:
            logger.warning("No valid accounts to sync")
            return {}

        date_str_start = start_date.strftime("%Y-%m-%d")
        date_str_end = end_date.strftime("%Y-%m-%d")
        logger.info("=== Backfill %s ~ %s, %d accounts ===",
                     date_str_start, date_str_end, len(account_ids))

        total_rows = 0
        results: dict[str, int] = {}

        # Step 1: Sync account-level reports (date range API)
        logger.info("--- Step 1: Account reports ---")
        for i, aid in enumerate(account_ids):
            try:
                rows = self.client.get_account_report_date_range(
                    aid, start_date, end_date,
                )
                if rows:
                    self.storage.ensure_account(aid)
                    count = self.storage.upsert_account_reports(aid, rows, delivery_type="total")
                    results[aid] = count
                    total_rows += count
                    logger.info("  [%d/%d] %s: %d account rows (total)",
                                i + 1, len(account_ids), aid[-8:], count)
                else:
                    logger.debug("  [%d/%d] %s: no account data", i + 1, len(account_ids), aid[-8:])
            except Exception as e:
                logger.warning("  [%d/%d] %s: account skip (%s)",
                               i + 1, len(account_ids), aid[-8:], e)

        logger.info("Account reports: %d rows total", total_rows)

        # Step 2: Sync promotion-level reports first (material sync needs promotion list)
        total_promo = self._batch_sync("promotion", date_str_start, date_str_end, account_ids)

        # Step 3: Sync material-level reports (uses promotion info for attribution)
        total_mat = self._batch_sync("material", date_str_start, date_str_end, account_ids)

        # Step 4: Sync project-level reports
        total_project = self._batch_sync("project", date_str_start, date_str_end, account_ids)

        # Step 5: Refresh account names
        self.refresh_account_names(account_ids)

        # Step 6: Reconciliation — detect gaps from deleted entities
        self._reconciliation_check(date_str_start, date_str_end, account_ids)

        # Step 7: Completeness check
        self._completeness_check(date_str_start, date_str_end, account_ids, results)

        logger.info("=== Backfill complete: %d account rows, %d materials, %d promotions, %d projects ===",
                     total_rows, total_mat, total_promo, total_project)

        return results

    def _batch_sync(
        self,
        report_type: str,
        start_date: str,
        end_date: str,
        account_ids: list[str],
    ) -> int:
        """Sync material or promotion reports for a date range across all accounts.
        Includes retry with exponential backoff and inter-account delay."""
        label = {"material": "material", "promotion": "promotion", "project": "project"}.get(report_type, report_type)
        step_map = {"material": 2, "promotion": 3, "project": 4}
        step = step_map.get(report_type, 5)
        total = len(account_ids)
        grand_total = 0
        failed_accounts = []

        logger.info("--- Step %d: %s reports (retry=%d, delay=%.1fs) ---",
                     step, label.capitalize(), MAX_RETRIES, INTER_ACCOUNT_DELAY)

        for i, aid in enumerate(account_ids):
            success = False
            for attempt in range(MAX_RETRIES):
                try:
                    if report_type == "material":
                        # Use per-promotion sync with attribution
                        count = self._sync_account_materials(aid, start_date, end_date)
                        grand_total += count
                        if count > 0:
                            logger.info("  [%d/%d] %s: %d %s(s)",
                                        i + 1, total, aid[-8:], count, label)
                        else:
                            logger.debug("  [%d/%d] %s: no %s data",
                                         i + 1, total, aid[-8:], label)
                    elif report_type == "project":
                        rows = self.client.get_project_report(aid, start_date, end_date)
                        if rows:
                            count = self.storage.upsert_project_reports(aid, rows)
                            grand_total += count
                            logger.info("  [%d/%d] %s: %d %s(s)",
                                        i + 1, total, aid[-8:], count, label)
                        else:
                            logger.debug("  [%d/%d] %s: no %s data",
                                         i + 1, total, aid[-8:], label)
                    else:
                        rows = self.client.get_promotion_report(aid, start_date, end_date)
                        if rows:
                            count = self.storage.upsert_promotion_reports(aid, rows)
                            grand_total += count
                            logger.info("  [%d/%d] %s: %d %s(s)",
                                        i + 1, total, aid[-8:], count, label)
                        else:
                            logger.debug("  [%d/%d] %s: no %s data",
                                         i + 1, total, aid[-8:], label)
                    success = True
                    break  # success, no retry needed
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                        logger.warning("  [%d/%d] %s: %s attempt %d failed (%s), retry in %ds",
                                       i + 1, total, aid[-8:], label, attempt + 1, e, delay)
                        time.sleep(delay)
                    else:
                        logger.warning("  [%d/%d] %s: %s failed after %d attempts (%s)",
                                       i + 1, total, aid[-8:], label, MAX_RETRIES, e)
                        failed_accounts.append(aid)

            # Inter-account delay to avoid API rate limits
            if i < total - 1:
                time.sleep(INTER_ACCOUNT_DELAY)

        logger.info("%s reports: %d rows total, %d accounts failed",
                     label.capitalize(), grand_total, len(failed_accounts))
        return grand_total

    def _sync_delivery_types(
        self,
        aid: str,
        start_date: str,
        end_date: str,
    ) -> None:
        """
        [DEPRECATED 2026-06-28] 通投/搜索拆分已废弃。

        按 SKILL.md 规范，API 默认返回的就是通投+搜索全量数据，
        不应做二次拆分。该方法保留为空壳以兼容旧调用方，
        实际不做任何操作。详见 SKILL.md「数据源策略」铁律。

        历史问题：原实现会二次调 API（campaign_type=GENERAL），
        再用 total-general 减法计算"搜索"，违反"API 数据即最终结果"规范。
        """
        return None

    @staticmethod
    def _val(row: dict, key: str) -> float:
        """Safely get a numeric value from a dict. (Kept for compatibility.)"""
        v = row.get(key, 0)
        if v is None or v == "":
            return 0
        return float(v)

    def _reconciliation_check(
        self,
        start_date: str,
        end_date: str,
        account_ids: list[str],
    ) -> None:
        """
        Post-sync reconciliation: detect gaps between account-level total
        and promotion-level sum. Gaps may indicate deleted promotions/projects
        whose historical spend wasn't captured.

        If a gap > 0.1% is found, query deleted entity lists from API to
        help identify the root cause.
        """
        conn = self.storage._get_conn()
        total_gap = 0.0
        accounts_with_gap = 0

        for aid in account_ids:
            # Account total for the range
            acc_row = conn.execute(
                """
                SELECT SUM(stat_cost) as cost FROM account_reports
                WHERE account_id = ? AND stat_date BETWEEN ? AND ?
                """,
                (aid, start_date, end_date),
            ).fetchone()
            acc_cost = (acc_row["cost"] or 0) if acc_row else 0

            # Promotion total for the range
            promo_row = conn.execute(
                """
                SELECT SUM(stat_cost) as cost FROM promotion_reports
                WHERE account_id = ? AND stat_date BETWEEN ? AND ?
                """,
                (aid, start_date, end_date),
            ).fetchone()
            promo_cost = (promo_row["cost"] or 0) if promo_row else 0

            if acc_cost <= 0:
                continue

            gap = acc_cost - promo_cost
            gap_pct = gap / acc_cost * 100

            if abs(gap_pct) > 0.1:
                total_gap += gap
                accounts_with_gap += 1
                logger.warning(
                    "Reconcile: %s gap=¥%.2f (%.2f%%), account=¥%.2f, promo=¥%.2f",
                    aid[-8:], gap, gap_pct, acc_cost, promo_cost,
                )

        if accounts_with_gap > 0:
            logger.warning(
                "Reconciliation: %d accounts with gaps, total gap=¥%.2f — "
                "may indicate deleted promotions/projects. "
                "Use 'python ad.py 对账' to investigate further.",
                accounts_with_gap, total_gap,
            )
        else:
            logger.info(
                "Reconciliation: all %d accounts aligned (gap < 0.1%%)",
                len(account_ids),
            )

    def _completeness_check(
        self,
        start_date: str,
        end_date: str,
        account_ids: list[str],
        sync_results: dict[str, int],
    ) -> None:
        """Post-sync completeness check: verify all accounts have data."""
        conn = self.storage._get_conn()

        # Check account_reports
        rows = conn.execute(
            """
            SELECT account_id, COUNT(*) as cnt, SUM(stat_cost) as cost
            FROM account_reports
            WHERE stat_date BETWEEN ? AND ?
            GROUP BY account_id
            """,
            (start_date, end_date),
        ).fetchall()

        found_ids = {r["account_id"] for r in rows}
        missing_ids = set(account_ids) - found_ids
        zero_cost = [r for r in rows if (r["cost"] or 0) == 0]

        if missing_ids:
            logger.warning("Completeness: %d accounts missing from account_reports: %s",
                           len(missing_ids), [aid[-8:] for aid in missing_ids])
        if zero_cost:
            logger.warning("Completeness: %d accounts have zero cost in range %s~%s",
                           len(zero_cost), start_date, end_date)

        # Check material_reports
        mat_rows = conn.execute(
            "SELECT COUNT(DISTINCT account_id) as cnt FROM material_reports WHERE stat_date BETWEEN ? AND ?",
            (start_date, end_date),
        ).fetchone()
        if mat_rows and mat_rows["cnt"] < len(account_ids) * 0.5:
            logger.warning("Completeness: material_reports only covers %d/%d accounts",
                           mat_rows["cnt"], len(account_ids))

        # Check promotion_reports
        promo_rows = conn.execute(
            "SELECT COUNT(DISTINCT account_id) as cnt FROM promotion_reports WHERE stat_date BETWEEN ? AND ?",
            (start_date, end_date),
        ).fetchone()
        if promo_rows and promo_rows["cnt"] < len(account_ids) * 0.5:
            logger.warning("Completeness: promotion_reports only covers %d/%d accounts",
                           promo_rows["cnt"], len(account_ids))

        total_cost = sum(r["cost"] or 0 for r in rows)
        logger.info("Completeness: %d/%d accounts synced, total cost ¥%.0f, %d missing, %d zero-cost",
                     len(found_ids), len(account_ids), total_cost, len(missing_ids), len(zero_cost))

    # ── Quick Stats ────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get current database statistics."""
        accounts = self.storage.get_account_ids()
        latest_date = ""
        total_rows = 0
        material_rows = 0

        conn = self.storage._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt, MAX(stat_date) as latest FROM account_reports"
        ).fetchone()
        if row:
            total_rows = row["cnt"]
            latest_date = row["latest"] or ""

        mrow = conn.execute(
            "SELECT COUNT(*) as cnt FROM material_reports"
        ).fetchone()
        if mrow:
            material_rows = mrow["cnt"]

        return {
            "accounts": len(accounts),
            "total_rows": total_rows,
            "material_rows": material_rows,
            "latest_date": latest_date,
            "account_ids": accounts,
        }
