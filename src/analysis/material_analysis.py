"""
Material (Creative) Analysis Engine

Analyzes creative-level performance:
- Top/Bottom material ranking
- Material fatigue detection
- Zero-performance (浪费) materials
- Material type distribution
- CTR / conversion performance by material
"""

import logging
from datetime import date, timedelta
from typing import Optional

from src.pipeline.storage import Storage

logger = logging.getLogger(__name__)


class MaterialAnalyzer:
    """Analyze material (creative) performance data."""

    def __init__(self, storage: Optional[Storage] = None):
        self.storage = storage or Storage()

    def analyze_date(self, date_str: str) -> dict:
        """
        Full material analysis for a given date.

        Returns:
            {top_materials, bottom_materials, zero_perf_materials,
             type_distribution, summary_stats}
        """
        materials = self.storage.get_material_summary(date_str)

        if not materials:
            return {
                "date": date_str,
                "total_materials": 0,
                "top_materials": [],
                "bottom_materials": [],
                "zero_perf_materials": [],
                "type_distribution": {},
                "summary_stats": {},
            }

        # Sort by cost descending
        sorted_by_cost = sorted(materials, key=lambda m: m.get("total_cost", 0), reverse=True)

        # Top 10 by cost
        top_materials = sorted_by_cost[:10]

        # Bottom materials: those with cost > 10 and zero conversions
        bottom_materials = [
            m for m in materials
            if m.get("total_cost", 0) > 10
            and m.get("total_convert", 0) == 0
            and m.get("total_consult", 0) == 0
            and m.get("total_clue", 0) == 0
        ]
        bottom_materials.sort(key=lambda m: m.get("total_cost", 0), reverse=True)
        bottom_materials = bottom_materials[:10]

        # Zero performance materials (浪费)
        zero_perf = self.storage.get_zero_performance_materials(date_str)

        # Type distribution
        type_dist: dict[str, dict] = {}
        for m in materials:
            mtype = m.get("material_type", "UNKNOWN")
            if mtype not in type_dist:
                type_dist[mtype] = {"count": 0, "total_cost": 0, "total_show": 0, "total_convert": 0}
            t = type_dist[mtype]
            t["count"] += 1
            t["total_cost"] += m.get("total_cost", 0) or 0
            t["total_show"] += m.get("total_show", 0) or 0
            t["total_convert"] += m.get("total_convert", 0) or 0

        # Summary stats
        total_cost = sum(m.get("total_cost", 0) or 0 for m in materials)
        total_convert = sum(m.get("total_convert", 0) or 0 for m in materials)
        total_consult = sum(m.get("total_consult", 0) or 0 for m in materials)
        total_clue = sum(m.get("total_clue", 0) or 0 for m in materials)
        total_show = sum(m.get("total_show", 0) or 0 for m in materials)
        total_click = sum(m.get("total_click", 0) or 0 for m in materials)

        summary = {
            "total_materials": len(materials),
            "total_cost": total_cost,
            "total_show": total_show,
            "total_click": total_click,
            "total_convert": total_convert,
            "total_consult": total_consult,
            "total_clue": total_clue,
            "avg_ctr": round(total_click / total_show * 100, 2) if total_show > 0 else 0,
            "avg_cpa": round(total_cost / total_clue, 2) if total_clue > 0 else 0,
            "waste_cost": sum(m.get("total_cost", 0) or 0 for m in zero_perf),
            "waste_count": len(zero_perf),
        }

        return {
            "date": date_str,
            "total_materials": len(materials),
            "top_materials": top_materials,
            "bottom_materials": bottom_materials,
            "zero_perf_materials": zero_perf,
            "type_distribution": type_dist,
            "summary_stats": summary,
        }

    def detect_material_fatigue(
        self,
        account_id: Optional[str] = None,
        days: int = 14,
    ) -> list[dict]:
        """
        Detect materials showing CTR degradation over time.

        A material is "fatigued" if its recent 3-day CTR is
        significantly lower than its peak 3-day CTR in the period.
        """
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)

        all_materials = self.storage.get_material_reports(
            account_id=account_id,
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            limit=2000,
        )

        if not all_materials:
            return []

        # Group by material_id
        from collections import defaultdict
        mat_data: dict[str, list[dict]] = defaultdict(list)
        for row in all_materials:
            mat_data[row["material_id"]].append(row)

        fatigued = []
        for mid, rows in mat_data.items():
            rows.sort(key=lambda r: r["stat_date"])

            # Need at least 6 days of data
            if len(rows) < 6:
                continue

            # Recent 3 days vs peak 3 days
            recent = rows[-3:]
            peak_ctr = 0
            for i in range(len(rows) - 2):
                window = rows[i:i + 3]
                avg_ctr = sum(r.get("ctr", 0) or 0 for r in window) / 3
                peak_ctr = max(peak_ctr, avg_ctr)

            recent_ctr = sum(r.get("ctr", 0) or 0 for r in recent) / 3

            if peak_ctr > 0 and recent_ctr / peak_ctr < 0.5:
                total_cost = sum(r.get("stat_cost", 0) or 0 for r in rows)
                fatigued.append({
                    "material_id": mid,
                    "material_name": rows[0].get("material_name", ""),
                    "account_id": rows[0].get("account_id", ""),
                    "account_name": rows[0].get("account_name", ""),
                    "recent_ctr": round(recent_ctr, 2),
                    "peak_ctr": round(peak_ctr, 2),
                    "degradation_pct": round((1 - recent_ctr / peak_ctr) * 100, 1) if peak_ctr > 0 else 0,
                    "total_cost_14d": round(total_cost, 0),
                    "type": "MATERIAL_FATIGUE",
                })

        fatigued.sort(key=lambda f: f["total_cost_14d"], reverse=True)
        return fatigued[:10]

    def get_top_materials_ranking(
        self,
        start_date: str,
        end_date: str,
        top_n: int = 15,
        metric: str = "total_cost",
    ) -> list[dict]:
        """Get top materials ranked by a given metric in a date range."""
        ranking = self.storage.get_material_ranking(start_date, end_date, top_n)
        return ranking[:top_n]
