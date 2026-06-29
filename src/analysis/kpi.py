"""
KPI Calculation Engine (Account-Centric)

Computes key performance metrics across all local ad accounts:
- Daily / period summaries
- Account ranking by cost, ROI, CPA
- Trend analysis
- Period comparison
"""

import logging
from datetime import date, timedelta
from typing import Optional

from src.pipeline.storage import Storage

logger = logging.getLogger(__name__)


class KPIAnalyzer:
    """Compute and compare KPIs across accounts and time periods."""

    def __init__(self, storage: Optional[Storage] = None):
        self.storage = storage or Storage()

    # ── Daily Summary ──────────────────────────────────────────

    def daily_summary(self, target_date: Optional[date] = None) -> dict:
        """Get KPI summary for a single day across all accounts."""
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        date_str = target_date.strftime("%Y-%m-%d")
        return self.storage.get_daily_summary(date_str)

    def account_daily_summary(self, account_id: str, target_date: Optional[date] = None) -> dict:
        """Get KPI summary for a single account on a given day."""
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        date_str = target_date.strftime("%Y-%m-%d")
        return self.storage.get_daily_summary(date_str, account_id=account_id)

    # ── Trend Analysis ─────────────────────────────────────────

    def trend(self, days: int = 7, account_id: Optional[str] = None) -> list[dict]:
        """Get daily KPI trend for the last N days."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        return self.storage.get_trend(
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            account_id=account_id,
        )

    # ── Account Ranking ────────────────────────────────────────

    def account_ranking(
        self,
        metric: str = "cost",
        days: int = 7,
        top_n: int = 10,
    ) -> list[dict]:
        """Rank accounts by a given metric over N days."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)

        conn = self.storage._get_conn()
        metric_col = {
            "cost": "SUM(r.stat_cost)",
            "show": "SUM(r.show_cnt)",
            "click": "SUM(r.click_cnt)",
            "convert": "SUM(r.convert_cnt)",
            "ctr": "CASE WHEN SUM(r.show_cnt) > 0 THEN ROUND(SUM(r.click_cnt)*100.0/SUM(r.show_cnt), 2) END",
            "cvr": "CASE WHEN SUM(r.click_cnt) > 0 THEN ROUND(SUM(r.convert_cnt)*100.0/SUM(r.click_cnt), 2) END",
            "cpa": "CASE WHEN SUM(r.clue_message_count) > 0 THEN ROUND(SUM(r.stat_cost)/SUM(r.clue_message_count), 2) END",
            "lead_cpa": "CASE WHEN SUM(r.clue_message_count) > 0 THEN ROUND(SUM(r.stat_cost)/SUM(r.clue_message_count), 2) END",
            "consult": "SUM(r.message_action_cnt)",
            "clue": "SUM(r.clue_message_count)",
        }.get(metric, "SUM(r.stat_cost)")

        rows = conn.execute(
            f"""
            SELECT
                r.account_id,
                a.name as account_name,
                SUM(r.stat_cost) as total_cost,
                SUM(r.show_cnt) as total_show,
                SUM(r.click_cnt) as total_click,
                SUM(r.convert_cnt) as total_convert,
                SUM(r.message_action_cnt) as total_consult,
                SUM(r.clue_message_count) as total_clue,
                CASE WHEN SUM(r.show_cnt) > 0
                    THEN ROUND(SUM(r.click_cnt)*100.0/SUM(r.show_cnt), 2) END as ctr,
                CASE WHEN SUM(r.click_cnt) > 0
                    THEN ROUND(SUM(r.convert_cnt)*100.0/SUM(r.click_cnt), 2) END as cvr,
                CASE WHEN SUM(r.clue_message_count) > 0
                    THEN ROUND(SUM(r.stat_cost)/SUM(r.clue_message_count), 2) END as cpa,
                CASE WHEN SUM(r.clue_message_count) > 0
                    THEN ROUND(SUM(r.stat_cost)/SUM(r.clue_message_count), 2) END as lead_cpa
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date BETWEEN ? AND ?
            GROUP BY r.account_id
            ORDER BY {metric_col} DESC
            LIMIT ?
            """,
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), top_n),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Period Comparison ──────────────────────────────────────

    def compare_periods(
        self,
        current_start: date,
        current_end: date,
        previous_start: date,
        previous_end: date,
        account_id: Optional[str] = None,
    ) -> dict:
        """Compare two date ranges side-by-side with change percentages."""
        def query_period(sd: date, ed: date) -> dict:
            conditions = ["stat_date BETWEEN ? AND ?"]
            params = [sd.strftime("%Y-%m-%d"), ed.strftime("%Y-%m-%d")]
            if account_id:
                conditions.append("account_id = ?")
                params.append(account_id)

            where = " AND ".join(conditions)
            conn = self.storage._get_conn()
            row = conn.execute(
                f"""
                SELECT
                    SUM(stat_cost) as total_cost,
                    SUM(show_cnt) as total_show,
                    SUM(click_cnt) as total_click,
                    SUM(convert_cnt) as total_convert,
                    SUM(message_action_cnt) as total_consult,
                    SUM(clue_message_count) as total_clue,
                    CASE WHEN SUM(show_cnt) > 0 THEN ROUND(SUM(click_cnt)*100.0/SUM(show_cnt),2) END as ctr,
                    CASE WHEN SUM(click_cnt) > 0 THEN ROUND(SUM(convert_cnt)*100.0/SUM(click_cnt),2) END as cvr,
                    CASE WHEN SUM(clue_message_count) > 0 THEN ROUND(SUM(stat_cost)/SUM(clue_message_count),2) END as cpa,
                    CASE WHEN SUM(clue_message_count) > 0 THEN ROUND(SUM(stat_cost)/SUM(clue_message_count),2) END as lead_cpa
                FROM account_reports
                WHERE {where}
                """,
                params,
            ).fetchone()
            return dict(row) if row else {}

        current = query_period(current_start, current_end)
        previous = query_period(previous_start, previous_end)

        def pct_change(new, old):
            try:
                nv, ov = float(new or 0), float(old or 0)
                if ov == 0:
                    return None if nv == 0 else float("inf")
                return round((nv - ov) / ov * 100, 2)
            except (ValueError, TypeError):
                return None

        return {
            "current_period": {"start": str(current_start), "end": str(current_end), **current},
            "previous_period": {"start": str(previous_start), "end": str(previous_end), **previous},
            "changes": {
                "cost_pct": pct_change(current.get("total_cost"), previous.get("total_cost")),
                "show_pct": pct_change(current.get("total_show"), previous.get("total_show")),
                "click_pct": pct_change(current.get("total_click"), previous.get("total_click")),
                "convert_pct": pct_change(current.get("total_convert"), previous.get("total_convert")),
                "consult_pct": pct_change(current.get("total_consult"), previous.get("total_consult")),
                "clue_pct": pct_change(current.get("total_clue"), previous.get("total_clue")),
            },
        }
