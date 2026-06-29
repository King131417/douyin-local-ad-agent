"""
Attribution Analysis (Account-Centric)

Analyzes performance changes by contributing factor:
- Day-of-week patterns per account
- Audience saturation (rising CPA with stable impressions)
- Account-level cost efficiency trends
"""

import logging
from datetime import date, timedelta
from typing import Optional

from src.pipeline.storage import Storage

logger = logging.getLogger(__name__)


class AttributionAnalyzer:
    """Multi-dimensional attribution analysis for ad performance."""

    def __init__(self, storage: Optional[Storage] = None):
        self.storage = storage or Storage()

    def day_of_week_analysis(self, days: int = 28, account_id: Optional[str] = None) -> dict:
        """Analyze performance patterns by day of week."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)

        conn = self.storage._get_conn()
        conditions = ["stat_date BETWEEN ? AND ?"]
        params = [start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")]
        if account_id:
            conditions.append("account_id = ?")
            params.append(account_id)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"""
            SELECT
                strftime('%w', stat_date) as dow,
                AVG(stat_cost) as avg_cost,
                AVG(show_cnt) as avg_show,
                AVG(click_cnt) as avg_click,
                AVG(convert_cnt) as avg_convert,
                AVG(message_action_cnt) as avg_consult,
                AVG(clue_message_count) as avg_clue,
                AVG(ctr) as avg_ctr,
                AVG(cvr) as avg_cvr,
                AVG(cpa) as avg_cpa
            FROM account_reports
            WHERE {where}
            GROUP BY dow
            ORDER BY dow
            """,
            params,
        ).fetchall()

        dow_names = {
            "0": "周日", "1": "周一", "2": "周二", "3": "周三",
            "4": "周四", "5": "周五", "6": "周六",
        }

        result = {}
        for row in rows:
            r = dict(row)
            r["day_name"] = dow_names.get(r["dow"], r["dow"])
            # Round for readability
            for k in ("avg_cost", "avg_ctr", "avg_cvr", "avg_cpa"):
                if r.get(k):
                    r[k] = round(r[k], 2)
            result[r["dow"]] = r
        return result

    def audience_saturation_check(self, days: int = 14, min_cost: float = 500) -> list[dict]:
        """Check for audience saturation: CPA rising while impressions flat."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        mid = start + timedelta(days=days // 2)

        conn = self.storage._get_conn()
        rows = conn.execute(
            """
            SELECT
                account_id,
                AVG(CASE WHEN stat_date < ? THEN stat_cost ELSE NULL END) as early_cost,
                AVG(CASE WHEN stat_date >= ? THEN stat_cost ELSE NULL END) as late_cost,
                CASE WHEN SUM(CASE WHEN stat_date < ? THEN convert_cnt ELSE 0 END) > 0
                     THEN SUM(CASE WHEN stat_date < ? THEN stat_cost ELSE 0 END)
                        / SUM(CASE WHEN stat_date < ? THEN convert_cnt ELSE 0 END)
                END as early_cpa,
                CASE WHEN SUM(CASE WHEN stat_date >= ? THEN convert_cnt ELSE 0 END) > 0
                     THEN SUM(CASE WHEN stat_date >= ? THEN stat_cost ELSE 0 END)
                        / SUM(CASE WHEN stat_date >= ? THEN convert_cnt ELSE 0 END)
                END as late_cpa,
                AVG(CASE WHEN stat_date < ? THEN show_cnt ELSE NULL END) as early_show,
                AVG(CASE WHEN stat_date >= ? THEN show_cnt ELSE NULL END) as late_show,
                SUM(stat_cost) as total_cost
            FROM account_reports
            WHERE stat_date BETWEEN ? AND ?
            GROUP BY account_id
            HAVING total_cost > ? AND early_cpa > 0 AND late_cpa > 0
            """,
            (mid.strftime("%Y-%m-%d"), mid.strftime("%Y-%m-%d"),
             mid.strftime("%Y-%m-%d"), mid.strftime("%Y-%m-%d"), mid.strftime("%Y-%m-%d"),
             mid.strftime("%Y-%m-%d"), mid.strftime("%Y-%m-%d"), mid.strftime("%Y-%m-%d"),
             mid.strftime("%Y-%m-%d"), mid.strftime("%Y-%m-%d"),
             start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
             min_cost),
        ).fetchall()

        results = []
        for row in rows:
            r = dict(row)
            cpa_rise = (r["late_cpa"] - r["early_cpa"]) / r["early_cpa"] * 100
            show_change = (r["late_show"] - r["early_show"]) / r["early_show"] * 100 if r["early_show"] else 0
            if cpa_rise > 15 and show_change > -10:
                results.append({
                    "account_id": r["account_id"],
                    "cpa_rise_pct": round(cpa_rise, 1),
                    "show_change_pct": round(show_change, 1),
                    "early_cpa": round(r["early_cpa"], 2),
                    "late_cpa": round(r["late_cpa"], 2),
                    "diagnosis": "人群饱和",
                    "suggestion": "建议扩展定向人群或更换兴趣标签",
                })

        results.sort(key=lambda x: x["cpa_rise_pct"], reverse=True)
        return results

    def cost_efficiency_trend(self, account_id: str, days: int = 14) -> dict:
        """Track cost per consultation/clue over time for an account."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)

        conn = self.storage._get_conn()
        rows = conn.execute(
            """
            SELECT
                stat_date,
                stat_cost,
                message_action_cnt,
                clue_message_count,
                CASE WHEN message_action_cnt > 0
                     THEN ROUND(stat_cost / message_action_cnt, 2) END as cost_per_consult,
                CASE WHEN clue_message_count > 0
                     THEN ROUND(stat_cost / clue_message_count, 2) END as cost_per_clue
            FROM account_reports
            WHERE account_id = ? AND stat_date BETWEEN ? AND ?
            ORDER BY stat_date
            """,
            (account_id, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()

        return {
            "account_id": account_id,
            "days": days,
            "trend": [dict(r) for r in rows],
        }
