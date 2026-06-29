"""
Anomaly Detection Module (Account-Centric)

Detects significant deviations in ad performance across accounts:
- Cost spikes/drops per account
- Zero-impression accounts with active spend
- CTR degradation
- Consultation/clue drops
"""

import logging
from datetime import date, timedelta
from typing import Optional

from config.settings import (
    ANOMALY_THRESHOLD_PCT,
    ANOMALY_MIN_COST,
    ANOMALY_LOOKBACK_DAYS,
)
from src.pipeline.storage import Storage

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detect anomalies in account-level ad performance data."""

    def __init__(self, storage: Optional[Storage] = None):
        self.storage = storage or Storage()

    def detect_all(self, target_date: Optional[date] = None) -> list[dict]:
        """Run all anomaly checks and return list of findings."""
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        anomalies = []
        anomalies.extend(self._cost_spike_check(target_date))
        anomalies.extend(self._zero_impression_check(target_date))
        anomalies.extend(self._consult_drop_check(target_date))
        anomalies.extend(self._ctr_degradation_check(target_date))
        anomalies.extend(self._lead_drop_check(target_date))
        anomalies.extend(self._lead_cpa_spike_check(target_date))

        logger.info("Detected %d anomalies for %s", len(anomalies), target_date)
        return anomalies

    def _cost_spike_check(self, target_date: date) -> list[dict]:
        """Detect accounts where cost deviated significantly from average."""
        date_str = target_date.strftime("%Y-%m-%d")
        lookback_start = (target_date - timedelta(days=ANOMALY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

        conn = self.storage._get_conn()
        rows = conn.execute(
            """
            SELECT
                r.account_id,
                a.name as account_name,
                SUM(CASE WHEN r.stat_date = ? THEN r.stat_cost ELSE 0 END) as today_cost,
                AVG(CASE WHEN r.stat_date < ? AND r.stat_cost > 0 THEN r.stat_cost ELSE NULL END) as avg_cost
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date >= ?
              AND r.delivery_type = 'total'
            GROUP BY r.account_id
            HAVING today_cost > ? AND avg_cost > 0
               AND ABS(today_cost - avg_cost) / avg_cost * 100 > ?
            """,
            (date_str, date_str, lookback_start,
             ANOMALY_MIN_COST, ANOMALY_THRESHOLD_PCT),
        ).fetchall()

        anomalies = []
        for row in rows:
            r = dict(row)
            pct = round((r["today_cost"] - r["avg_cost"]) / r["avg_cost"] * 100, 1)
            direction = "SPIKE" if pct > 0 else "DROP"
            account_name = r.get("account_name") or r["account_id"][-8:]
            anomalies.append({
                "type": f"COST_{direction}",
                "severity": "high" if abs(pct) > 50 else "medium",
                "account_id": r["account_id"],
                "account_name": account_name,
                "date": date_str,
                "detail": f"【{account_name}】消耗{'暴涨' if pct > 0 else '暴跌'} {abs(pct):.1f}% "
                          f"(当天 ¥{r['today_cost']:.0f} vs 均值 ¥{r['avg_cost']:.0f})",
            })
        return anomalies

    def _zero_impression_check(self, target_date: date) -> list[dict]:
        """Check for accounts with spend but zero impressions."""
        date_str = target_date.strftime("%Y-%m-%d")
        conn = self.storage._get_conn()
        rows = conn.execute(
            """
            SELECT r.account_id, a.name as account_name, r.stat_cost
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date = ?
              AND r.delivery_type = 'total' AND r.show_cnt = 0 AND r.stat_cost > 0
            """,
            (date_str,),
        ).fetchall()

        anomalies = []
        for row in rows:
            r = dict(row)
            anomalies.append({
                "type": "ZERO_IMPRESSION",
                "severity": "high",
                "account_id": r["account_id"],
                "account_name": r.get("account_name", r["account_id"][-8:]),
                "date": date_str,
                "detail": f"账户 {r.get('account_name', r['account_id'][-8:])} 有消耗(¥{r['stat_cost']:.0f})但无曝光",
            })
        return anomalies

    def _consult_drop_check(self, target_date: date) -> list[dict]:
        """Detect significant drops in consultation/clue counts."""
        date_str = target_date.strftime("%Y-%m-%d")
        lookback_start = (target_date - timedelta(days=ANOMALY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

        conn = self.storage._get_conn()
        rows = conn.execute(
            """
            SELECT
                r.account_id,
                a.name as account_name,
                SUM(CASE WHEN r.stat_date = ? THEN r.message_action_cnt ELSE 0 END) as today_consult,
                AVG(CASE WHEN r.stat_date < ? THEN r.message_action_cnt ELSE NULL END) as avg_consult,
                SUM(CASE WHEN r.stat_date = ? THEN r.stat_cost ELSE 0 END) as today_cost
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date >= ?
              AND r.delivery_type = 'total'
            GROUP BY r.account_id
            HAVING today_consult > 5 AND avg_consult > 10
               AND (avg_consult - today_consult) / avg_consult * 100 > ?
            """,
            (date_str, date_str, date_str, lookback_start, ANOMALY_THRESHOLD_PCT),
        ).fetchall()

        anomalies = []
        for row in rows:
            r = dict(row)
            pct = round((r["avg_consult"] - r["today_consult"]) / r["avg_consult"] * 100, 1)
            account_name = r.get("account_name") or r["account_id"][-8:]
            anomalies.append({
                "type": "CONSULT_DROP",
                "severity": "high" if pct > 50 else "medium",
                "account_id": r["account_id"],
                "account_name": account_name,
                "date": date_str,
                "detail": f"【{account_name}】咨询数下降 {pct:.1f}% "
                          f"(当天 {r['today_consult']} vs 均值 {r['avg_consult']:.0f})，"
                          f"当天消耗 ¥{r.get('today_cost',0):.0f}",
            })
        return anomalies

    def _ctr_degradation_check(self, target_date: date) -> list[dict]:
        """Detect significant CTR drops on high-impression accounts."""
        date_str = target_date.strftime("%Y-%m-%d")
        lookback_start = (target_date - timedelta(days=ANOMALY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

        conn = self.storage._get_conn()
        rows = conn.execute(
            """
            SELECT
                r.account_id,
                a.name as account_name,
                SUM(CASE WHEN r.stat_date = ? THEN r.show_cnt ELSE 0 END) as today_show,
                CASE WHEN SUM(CASE WHEN r.stat_date = ? THEN r.show_cnt ELSE 0 END) > 0
                     THEN SUM(CASE WHEN r.stat_date = ? THEN r.click_cnt ELSE 0 END) * 100.0
                        / SUM(CASE WHEN r.stat_date = ? THEN r.show_cnt ELSE 0 END)
                END as today_ctr,
                CASE WHEN SUM(CASE WHEN r.stat_date < ? THEN r.show_cnt ELSE 0 END) > 0
                     THEN SUM(CASE WHEN r.stat_date < ? THEN r.click_cnt ELSE 0 END) * 100.0
                        / SUM(CASE WHEN r.stat_date < ? THEN r.show_cnt ELSE 0 END)
                END as avg_ctr
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date >= ?
              AND r.delivery_type = 'total'
            GROUP BY r.account_id
            HAVING today_show > 1000 AND today_ctr < avg_ctr * (1 - ? / 100.0)
            """,
            (date_str, date_str, date_str, date_str, date_str, date_str, date_str,
             lookback_start, ANOMALY_THRESHOLD_PCT),
        ).fetchall()

        anomalies = []
        for row in rows:
            r = dict(row)
            pct = round((1 - r["today_ctr"] / r["avg_ctr"]) * 100, 1) if r["avg_ctr"] else 0
            anomalies.append({
                "type": "CTR_DEGRADATION",
                "severity": "medium",
                "account_id": r["account_id"],
                "account_name": r.get("account_name", r["account_id"][-8:]),
                "date": date_str,
                "detail": f"账户 {r.get('account_name', r['account_id'][-8:])} CTR下降{pct:.1f}% "
                          f"(当天 {r['today_ctr']:.2f}% vs 均值 {r['avg_ctr']:.2f}%)",
            })
        return anomalies

    def _lead_drop_check(self, target_date: date) -> list[dict]:
        """留资骤降：当天留资数 vs 前N天均值，降幅超阈值则告警。"""
        date_str = target_date.strftime("%Y-%m-%d")
        lookback_start = (target_date - timedelta(days=ANOMALY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

        conn = self.storage._get_conn()
        rows = conn.execute(
            """
            SELECT
                r.account_id,
                a.name as account_name,
                SUM(CASE WHEN r.stat_date = ? THEN r.clue_message_count ELSE 0 END) as today_clue,
                AVG(CASE WHEN r.stat_date < ? AND r.clue_message_count > 0 THEN r.clue_message_count ELSE NULL END) as avg_clue,
                SUM(CASE WHEN r.stat_date = ? THEN r.stat_cost ELSE 0 END) as today_cost
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date >= ?
              AND r.delivery_type = 'total'
            GROUP BY r.account_id
            HAVING today_clue >= 0 AND avg_clue > 3
               AND (avg_clue - today_clue) / avg_clue * 100 > ?
            """,
            (date_str, date_str, date_str, lookback_start, ANOMALY_THRESHOLD_PCT),
        ).fetchall()

        anomalies = []
        for row in rows:
            r = dict(row)
            today_clue = r.get("today_clue", 0)
            avg_clue = r.get("avg_clue", 0)
            if avg_clue <= 0:
                continue
            pct = round((avg_clue - today_clue) / avg_clue * 100, 1)
            account_name = r.get("account_name") or r["account_id"][-8:]
            anomalies.append({
                "type": "LEAD_DROP",
                "severity": "high" if pct > 50 else "medium",
                "account_id": r["account_id"],
                "account_name": account_name,
                "date": date_str,
                "detail": f"【{account_name}】留资数下降 {pct:.1f}% "
                          f"(当天 {today_clue} vs 均值 {avg_clue:.0f})，"
                          f"当天消耗 ¥{r.get('today_cost',0):.0f}",
            })
        return anomalies

    def _lead_cpa_spike_check(self, target_date: date) -> list[dict]:
        """转化成本(消耗/留资)飙升：当天留资CPA vs 前N天均值。"""
        date_str = target_date.strftime("%Y-%m-%d")
        lookback_start = (target_date - timedelta(days=ANOMALY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

        conn = self.storage._get_conn()
        rows = conn.execute(
            """
            SELECT
                r.account_id,
                a.name as account_name,
                SUM(CASE WHEN r.stat_date = ? THEN r.stat_cost ELSE 0 END) as today_cost,
                SUM(CASE WHEN r.stat_date = ? THEN r.clue_message_count ELSE 0 END) as today_clue,
                AVG(CASE WHEN r.stat_date < ? AND r.clue_message_count > 0
                         THEN r.stat_cost * 1.0 / r.clue_message_count ELSE NULL END) as avg_lead_cpa
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date >= ?
              AND r.delivery_type = 'total'
            GROUP BY r.account_id
            HAVING today_cost > ? AND today_clue > 0 AND avg_lead_cpa > 0
               AND (today_cost / today_clue) / avg_lead_cpa * 100 - 100 > ?
            """,
            (date_str, date_str, date_str, lookback_start,
             ANOMALY_MIN_COST, ANOMALY_THRESHOLD_PCT),
        ).fetchall()

        anomalies = []
        for row in rows:
            r = dict(row)
            today_clue = r.get("today_clue", 0)
            if today_clue <= 0:
                continue
            today_cpa = r["today_cost"] / today_clue
            avg_cpa = r.get("avg_lead_cpa", 0)
            if avg_cpa <= 0:
                continue
            pct = round((today_cpa / avg_cpa - 1) * 100, 1)
            account_name = r.get("account_name") or r["account_id"][-8:]
            anomalies.append({
                "type": "LEAD_CPA_SPIKE",
                "severity": "high" if pct > 50 else "medium",
                "account_id": r["account_id"],
                "account_name": account_name,
                "date": date_str,
                "detail": f"【{account_name}】转化成本飙升 {pct:.1f}% "
                          f"(当天 ¥{today_cpa:.0f}/留资 vs 均值 ¥{avg_cpa:.0f}/留资)，"
                          f"当天 {today_clue}留资、消耗 ¥{r['today_cost']:.0f}",
            })
        return anomalies
