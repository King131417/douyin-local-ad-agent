"""
Optimization Engine (Account-Centric)

Generates actionable suggestions based on account-level performance:
- Budget reallocation (scale winners, flag losers)
- Bidding optimization (CPA-based)
- Automated rules engine
"""

import logging
from datetime import date, timedelta
from typing import Optional

from config.settings import OPT_RULES
from src.pipeline.storage import Storage

logger = logging.getLogger(__name__)


class OptimizationEngine:
    """Generate optimization suggestions based on account performance data."""

    def __init__(self, storage: Optional[Storage] = None):
        self.storage = storage or Storage()

    def generate_suggestions(self, days: int = 7) -> list[dict]:
        """Run all optimization checks and return prioritized suggestions."""
        suggestions = []
        suggestions.extend(self._cost_efficiency_suggestions(days))
        suggestions.extend(self._consult_rate_suggestions(days))
        suggestions.extend(self._rule_engine(days))

        # Sort: high priority first
        suggestions.sort(key=lambda s: (
            0 if s.get("priority") == "high" else
            1 if "加预算" in str(s.get("action", "")) else
            2
        ))
        return suggestions

    def _cost_efficiency_suggestions(self, days: int) -> list[dict]:
        """Account-level cost efficiency analysis."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)

        conn = self.storage._get_conn()
        rows = conn.execute(
            """
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
                CASE WHEN SUM(r.message_action_cnt) > 0
                    THEN ROUND(SUM(r.stat_cost)/SUM(r.message_action_cnt), 2) END as cost_per_consult,
                CASE WHEN SUM(r.clue_message_count) > 0
                    THEN ROUND(SUM(r.stat_cost)/SUM(r.clue_message_count), 2) END as lead_cpa,
                AVG(r.stat_cost) as avg_daily_cost
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date BETWEEN ? AND ?
            GROUP BY r.account_id
            """,
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()

        suggestions = []
        for row in rows:
            r = dict(row)
            name = r.get("account_name") or r["account_id"][-8:]
            cost = r.get("total_cost") or 0
            ctr = r.get("ctr") or 0
            cvr = r.get("cvr") or 0
            cpa = r.get("cpa") or 0
            cp_consult = r.get("cost_per_consult") or 0
            cp_clue = r.get("lead_cpa") or 0
            total_clue = r.get("total_clue") or 0
            total_convert = r.get("total_convert") or 0

            # High spender with no conversions
            if cost > 500 and ctr < 0.5:
                suggestions.append({
                    "type": "LOW_CTR_WARNING",
                    "priority": "high",
                    "account_id": r["account_id"],
                    "account_name": name,
                    "total_cost": round(cost, 0),
                    "ctr": ctr,
                    "action": "建议检查投放定向和素材质量，CTR过低",
                    "reason": f"消耗 ¥{cost:.0f} 但 CTR 仅 {ctr:.2f}%，点击率严重偏低",
                })

            # High cost per consult
            if cp_consult > 100 and cost > 300:
                suggestions.append({
                    "type": "HIGH_COST_PER_CONSULT",
                    "priority": "medium",
                    "account_id": r["account_id"],
                    "account_name": name,
                    "cost_per_consult": cp_consult,
                    "total_consult": r.get("total_consult", 0),
                    "action": "咨询成本过高，建议优化投放时段或定向策略",
                    "reason": f"单次咨询成本 ¥{cp_consult:.0f}，高于合理区间",
                })

            # High cost per clue (留资) — 主CPA规则
            if cp_clue > 150 and cost > 300:
                suggestions.append({
                    "type": "HIGH_COST_PER_CLUE",
                    "priority": "medium",
                    "account_id": r["account_id"],
                    "account_name": name,
                    "lead_cpa": cp_clue,
                    "total_clue": total_clue,
                    "action": "留资成本偏高，建议优化落地页转化路径或调整定向人群",
                    "reason": f"单次留资成本 ¥{cp_clue:.0f}（{total_clue}留资），高于合理区间",
                })

            # 🪤 陷阱检测：咨询成本低但留资率(留资/咨询)差
            consult_cpa = r.get("cost_per_consult") or 0
            total_consult = r.get("total_consult") or 0
            if cost > 300 and consult_cpa > 0 and cp_clue > 0 and total_consult > 0:
                lead_consult_ratio = (total_clue / total_consult * 100) if total_consult > 0 else 0
                if consult_cpa < cp_clue * 0.5 and lead_consult_ratio < 50:
                    suggestions.append({
                        "type": "TRAP_CHEAP_CONSULT_BAD_LEAD",
                        "priority": "high",
                        "account_id": r["account_id"],
                        "account_name": name,
                        "consult_cpa": round(consult_cpa, 1),
                        "lead_cpa": cp_clue,
                        "lead_consult_rate": round(lead_consult_ratio, 0),
                        "action": "咨询成本低但留资率差，检查私信话术/留资链路，优化咨询→留资转化",
                        "reason": f"咨询成本 ¥{consult_cpa:.0f}→转化成本 ¥{cp_clue:.0f}，留资率(留资/咨询)仅{lead_consult_ratio:.0f}%",
                    })

            # 有消耗但零留资 = 高风险
            if cost > 200 and total_clue == 0:
                suggestions.append({
                    "type": "NO_LEAD_WARNING",
                    "priority": "high",
                    "account_id": r["account_id"],
                    "account_name": name,
                    "total_cost": round(cost, 0),
                    "action": "有消耗但零留资，建议排查落地页/留资链路或暂停投放",
                    "reason": f"消耗 ¥{cost:.0f} 但零留资，需排查",
                })

            # Good CTR but low CVR → landing page issue
            if ctr > 2 and cvr < 0.5 and r.get("total_click", 0) > 50:
                suggestions.append({
                    "type": "LANDING_PAGE_ISSUE",
                    "priority": "high",
                    "account_id": r["account_id"],
                    "account_name": name,
                    "ctr": ctr,
                    "cvr": cvr,
                    "action": "点击率高但转化率极低，建议检查落地页加载速度与内容匹配度",
                    "reason": f"CTR {ctr:.1f}% 但 CVR 仅 {cvr:.1f}%，落地页有严重问题",
                })

        return suggestions

    def _consult_rate_suggestions(self, days: int) -> list[dict]:
        """Analyze consultation rate trends."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        # Compare with previous period
        prev_start = start - timedelta(days=days)
        prev_end = start - timedelta(days=1)

        conn = self.storage._get_conn()
        # Current period
        curr_rows = conn.execute(
            """
            SELECT account_id, SUM(message_action_cnt) as total_consult,
                   SUM(stat_cost) as total_cost,
                   CASE WHEN SUM(stat_cost) > 0
                        THEN ROUND(SUM(message_action_cnt)*1.0/SUM(stat_cost)*100, 2) END as consult_rate
            FROM account_reports
            WHERE stat_date BETWEEN ? AND ? AND stat_cost > 0
            GROUP BY account_id
            """,
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()

        curr_map = {}
        for row in curr_rows:
            r = dict(row)
            if r.get("total_consult", 0) > 10:
                curr_map[r["account_id"]] = r

        # Previous period
        prev_rows = conn.execute(
            """
            SELECT account_id, SUM(message_action_cnt) as total_consult,
                   SUM(stat_cost) as total_cost,
                   CASE WHEN SUM(stat_cost) > 0
                        THEN ROUND(SUM(message_action_cnt)*1.0/SUM(stat_cost)*100, 2) END as consult_rate
            FROM account_reports
            WHERE stat_date BETWEEN ? AND ? AND stat_cost > 0
            GROUP BY account_id
            """,
            (prev_start.strftime("%Y-%m-%d"), prev_end.strftime("%Y-%m-%d")),
        ).fetchall()

        prev_map = {dict(r)["account_id"]: dict(r) for r in prev_rows}
        name_map = self.storage.get_account_name_map()

        suggestions = []
        for aid, curr in curr_map.items():
            prev = prev_map.get(aid)
            if prev and prev.get("consult_rate") and curr.get("consult_rate"):
                change = (curr["consult_rate"] - prev["consult_rate"]) / prev["consult_rate"] * 100
                if change < -20:
                    suggestions.append({
                        "type": "CONSULT_RATE_DROP",
                        "priority": "high",
                        "account_id": aid,
                        "account_name": name_map.get(aid, "account_" + aid[-8:]),
                        "consult_rate_change": round(change, 1),
                        "action": "咨询率持续下降，建议检查投放时段和出价策略",
                        "reason": f"咨询率下降 {abs(change):.1f}% (当前{curr['consult_rate']:.2f} vs 上期{prev['consult_rate']:.2f})",
                    })

        return suggestions

    def _rule_engine(self, days: int) -> list[dict]:
        """Apply configured optimization rules."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)

        conn = self.storage._get_conn()
        suggestions = []

        # Rule: low ROI / high spend (account-level) — 改用留资CPA
        rows = conn.execute(
            """
            SELECT r.account_id, a.name as account_name, SUM(r.stat_cost) as total_cost,
                   SUM(r.convert_cnt) as total_convert,
                   SUM(r.clue_message_count) as total_clue,
                   CASE WHEN SUM(r.clue_message_count) > 0
                        THEN ROUND(SUM(r.stat_cost)/SUM(r.clue_message_count), 2) END as cpa,
                   CASE WHEN SUM(r.clue_message_count) > 0
                        THEN ROUND(SUM(r.stat_cost)/SUM(r.clue_message_count), 2) END as lead_cpa,
                   CASE WHEN SUM(r.show_cnt) > 0
                        THEN ROUND(SUM(r.click_cnt)*100.0/SUM(r.show_cnt), 2) END as ctr
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date BETWEEN ? AND ?
            GROUP BY r.account_id
            HAVING total_cost > 500
            """,
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()

        for row in rows:
            r = dict(row)
            total_clue = r.get("total_clue") or 0
            lead_cpa = r.get("lead_cpa") or 0
            cost = r.get("total_cost") or 0
            ctr = r.get("ctr") or 0

            # Rule 1: CTR过低 + 有消耗 → 排查
            if ctr < 1.0:
                suggestions.append({
                    "type": "RULE_LOW_CTR",
                    "priority": "high",
                    "account_id": r["account_id"],
                    "account_name": r.get("account_name") or "account_" + r["account_id"][-8:],
                    "total_cost": round(cost, 0),
                    "ctr": ctr,
                    "action": "建议暂停该账户投放并排查原因",
                    "reason": f"消耗 ¥{cost:.0f} 但 CTR 低于 1%，需检查素材和定向",
                })

            # Rule 2: 留资CPA过高
            if lead_cpa > 200 and cost > 500:
                suggestions.append({
                    "type": "RULE_HIGH_LEAD_CPA",
                    "priority": "high",
                    "account_id": r["account_id"],
                    "account_name": r.get("account_name") or "account_" + r["account_id"][-8:],
                    "lead_cpa": lead_cpa,
                    "total_clue": total_clue,
                    "action": "留资成本过高，建议降低出价或优化留资转化路径",
                    "reason": f"转化成本 ¥{lead_cpa:.0f}（{total_clue}留资），超出合理范围",
                })

            # Rule 3: 有消耗零留资
            if cost > 200 and total_clue == 0:
                suggestions.append({
                    "type": "RULE_ZERO_LEAD",
                    "priority": "high",
                    "account_id": r["account_id"],
                    "account_name": r.get("account_name") or "account_" + r["account_id"][-8:],
                    "total_cost": round(cost, 0),
                    "action": "有消耗但零留资，强烈建议暂停排查",
                    "reason": f"消耗 ¥{cost:.0f} 但零留资",
                })

        # Rule: high lead CPA (账户级，阈值200) — 已合并到上面

        return suggestions
