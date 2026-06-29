"""
Ad Agent — Natural Language Interaction Layer

Routes natural language queries to the right analysis modules.
Supports: daily reports, anomaly alerts, optimization suggestions,
account rankings, trend analysis, period comparison.
"""

import json
import logging
import urllib.request
from datetime import date, timedelta
from typing import Optional

from config.settings import WECOM_WEBHOOK_URL, FEISHU_WEBHOOK_URL
from src.analysis import KPIAnalyzer, AnomalyDetector, AttributionAnalyzer
from src.analysis.material_analysis import MaterialAnalyzer
from src.optimization import OptimizationEngine

logger = logging.getLogger(__name__)


class AdAgent:
    """Natural language interface for local ad analytics."""

    def __init__(self):
        self.kpi = KPIAnalyzer()
        self.anomaly = AnomalyDetector()
        self.attribution = AttributionAnalyzer()
        self.optimizer = OptimizationEngine()
        self.material = MaterialAnalyzer()

    # ── Query Router ───────────────────────────────────────────

    def query(self, text: str) -> str:
        """Route a natural language query to the appropriate handler."""
        text_lower = text.lower()

        if any(w in text_lower for w in ["异常", "告警", "报警", "问题排查"]):
            return self._handle_anomaly_query()
        if any(w in text_lower for w in ["优化", "建议", "怎么调", "如何提升", "怎么优化"]):
            return self._handle_optimization_query()
        if any(w in text_lower for w in ["排名", "排行榜", "top", "最高", "最低", "哪个", "哪些"]):
            if any(w in text_lower for w in ["素材", "视频", "创意", "图片"]):
                return self._handle_material_ranking_query(text)
            return self._handle_ranking_query(text)
        if any(w in text_lower for w in ["素材", "视频", "创意", "素材id", "素材分析", "素材排名", "素材疲劳", "素材异常", "哪个素材", "最好素材", "最差素材"]):
            return self._handle_material_query(text)
        if any(w in text_lower for w in ["日报", "报告", "总结", "汇报"]):
            return self._handle_report_query(text)
        if any(w in text_lower for w in ["趋势", "走势", "变化"]):
            return self._handle_trend_query(text)
        if any(w in text_lower for w in ["对比", "环比", "同比", "比较", "vs"]):
            return self._handle_compare_query()
        return self._handle_summary_query()

    # ── Handlers ───────────────────────────────────────────────

    def _handle_summary_query(self) -> str:
        """Generate an overview of current ad performance."""
        summary = self.kpi.daily_summary()
        if not summary or not summary.get("total_cost"):
            return "📊 暂无今日数据，请先同步数据：`python main.py sync`"

        lines = [
            "📊 **投放数据概览**",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 消耗 | ¥{summary.get('total_cost', 0):,.0f} |",
            f"| 展示 | {summary.get('total_show', 0):,} |",
            f"| 点击 | {summary.get('total_click', 0):,} |",
            f"| 转化 | {summary.get('total_convert', 0):,} |",
            f"| 咨询 | {summary.get('total_consult', 0):,} |",
            f"| 留资 | {summary.get('total_clue', 0):,} |",
            f"| CTR | {summary.get('ctr', 0):.2f}% |",
            f"| CVR | {summary.get('cvr', 0):.2f}% |",
            f"| CPA | ¥{summary.get('cpa', 0):.2f} |",
            f"| 活跃账户 | {summary.get('account_count', 0)} |",
            "",
            f"💡 输入 **异常** 查看告警，**优化** 获取建议，**排名** 查看账户排行",
        ]
        return "\n".join(lines)

    def _handle_anomaly_query(self) -> str:
        """Report detected anomalies."""
        anomalies = self.anomaly.detect_all()
        if not anomalies:
            return "✅ 未检测到异常，各项指标正常。"

        lines = ["🚨 **异常告警**", ""]
        for a in anomalies[:10]:
            sev = "🔴" if a.get("severity") == "high" else "🟡"
            lines.append(f"{sev} **{a['type']}** — {a.get('account_name', a.get('account_id', '')[-8:])}")
            lines.append(f"   {a['detail']}")
            lines.append("")
        if len(anomalies) > 10:
            lines.append(f"*...还有 {len(anomalies)-10} 条告警*")
        return "\n".join(lines)

    def _handle_optimization_query(self) -> str:
        """Generate optimization suggestions."""
        suggestions = self.optimizer.generate_suggestions()
        if not suggestions:
            return "✅ 当前各项指标正常，暂无优化建议。"

        lines = ["💡 **优化建议 Top 10**", ""]
        for i, s in enumerate(suggestions[:10], 1):
            priority = "🔴" if s.get("priority") == "high" else "🟡"
            lines.append(f"{i}. {priority} {s['type']} — {s.get('account_name', '')}")
            lines.append(f"   📌 {s.get('action', '')}")
            lines.append(f"   📝 {s.get('reason', '')}")
            lines.append("")
        if len(suggestions) > 10:
            lines.append(f"*...还有 {len(suggestions)-10} 条建议*")
        return "\n".join(lines)

    def _handle_ranking_query(self, text: str) -> str:
        """Show account rankings."""
        metric = "cost"
        if "咨询" in text or "私信" in text:
            metric = "consult"
        elif "留资" in text or "线索" in text:
            metric = "clue"
        elif "转化" in text:
            metric = "convert"
        elif "点击" in text:
            metric = "click"
        elif "cpa" in text.lower():
            metric = "cpa"

        top_n = 10
        ranking = self.kpi.account_ranking(metric=metric, top_n=top_n)

        if not ranking:
            return "暂无排行数据。"

        metric_names = {
            "cost": "消耗", "click": "点击", "convert": "转化",
            "consult": "咨询", "clue": "留资", "cpa": "CPA",
        }
        metric_name = metric_names.get(metric, metric)

        lines = [f"📊 **{metric_name}排行 Top {top_n}**", ""]
        lines.append(f"| 排名 | 账户 | 消耗 | 展示 | 咨询 | 留资 | CTR | CPA |")
        lines.append(f"|------|------|------|------|------|------|------|------|")
        for i, r in enumerate(ranking, 1):
            name = r.get("account_name") or r["account_id"][-8:]
            lines.append(
                f"| {i} | {name} | ¥{r.get('total_cost',0):,.0f} | "
                f"{r.get('total_show',0):,} | {r.get('total_consult',0)} | "
                f"{r.get('total_clue',0)} | {r.get('ctr',0):.1f}% | "
                f"¥{r.get('cpa',0):.0f} |"
            )
        return "\n".join(lines)

    def _handle_report_query(self, text: str) -> str:
        """Generate daily or weekly report."""
        if "周" in text or "weekly" in text.lower():
            return self.generate_weekly_report()
        return self.generate_daily_report()

    def _handle_trend_query(self, text: str) -> str:
        """Show trend data."""
        import re
        days = 7
        m = re.search(r'(\d+)天', text)
        if m:
            days = int(m.group(1))

        trend = self.kpi.trend(days=days)
        if not trend:
            return "暂无趋势数据。"

        lines = [f"📈 **近{days}天趋势**", ""]
        lines.append(f"| 日期 | 消耗 | 展示 | 咨询 | 留资 | CTR | CPA |")
        lines.append(f"|------|------|------|------|------|------|------|")
        for r in trend:
            lines.append(
                f"| {r['stat_date']} | ¥{r.get('total_cost',0):,.0f} | "
                f"{r.get('total_show',0):,} | {r.get('total_consult',0)} | "
                f"{r.get('total_clue',0)} | {r.get('ctr',0):.1f}% | "
                f"¥{r.get('cpa',0):.0f} |"
            )
        return "\n".join(lines)

    def _handle_compare_query(self) -> str:
        """Compare current week vs last week."""
        today = date.today()
        curr_start = today - timedelta(days=6)
        curr_end = today - timedelta(days=1)
        prev_start = curr_start - timedelta(days=7)
        prev_end = curr_start - timedelta(days=1)

        result = self.kpi.compare_periods(curr_start, curr_end, prev_start, prev_end)

        changes = result.get("changes", {})
        current = result.get("current_period", {})
        previous = result.get("previous_period", {})

        def arrow(pct):
            if pct is None:
                return "—"
            if pct == float("inf"):
                return "🆕"
            return f"🔺{pct:.1f}%" if pct > 0 else f"🔻{abs(pct):.1f}%"

        lines = [
            "📊 **周度对比**",
            "",
            f"| 指标 | 本周 | 上周 | 变化 |",
            f"|------|------|------|------|",
            f"| 消耗 | ¥{current.get('total_cost',0):,.0f} | ¥{previous.get('total_cost',0):,.0f} | {arrow(changes.get('cost_pct'))} |",
            f"| 展示 | {current.get('total_show',0):,} | {previous.get('total_show',0):,} | {arrow(changes.get('show_pct'))} |",
            f"| 咨询 | {current.get('total_consult',0):,} | {previous.get('total_consult',0):,} | {arrow(changes.get('consult_pct'))} |",
            f"| 留资 | {current.get('total_clue',0):,} | {previous.get('total_clue',0):,} | {arrow(changes.get('clue_pct'))} |",
        ]
        return "\n".join(lines)

    # ── Material Handlers ──────────────────────────────────────

    def _handle_material_query(self, text: str) -> str:
        """Handle material-related natural language queries."""
        import re
        
        # Try to extract material ID from query
        id_match = re.search(r'(\d{15,20})', text)
        if id_match:
            return self._handle_material_search(id_match.group(1))
        
        # Material analysis for latest date
        if any(w in text for w in ["分析", "概况", "概览", "总结"]):
            return self._material_overview()
        
        # Fatigue detection
        if any(w in text for w in ["疲劳", "衰退", "下滑", "下降"]):
            return self._material_fatigue_report()
        
        # Default: top materials summary
        return self._material_overview()

    def _handle_material_search(self, material_id: str) -> str:
        """Search for a specific material by ID."""
        import sqlite3, json
        conn = sqlite3.connect(self.material.storage.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Exact match
        c.execute("""SELECT * FROM material_reports WHERE material_id = ? 
                    ORDER BY stat_date DESC LIMIT 7""", (material_id,))
        rows = c.fetchall()
        
        if not rows:
            # Try partial match
            c.execute("""SELECT DISTINCT material_id, material_name FROM material_reports 
                        WHERE material_id LIKE ? LIMIT 5""", (f'%{material_id[-12:]}%',))
            partials = c.fetchall()
            if partials:
                lines = [f"🔍 未找到完整ID，可能的匹配:", ""]
                for p in partials:
                    lines.append(f"- `{p['material_id']}` — {p['material_name'][:40]}")
                conn.close()
                return "\n".join(lines)
            conn.close()
            return f"❌ 未找到素材ID `{material_id}`"
        
        first = rows[0]
        
        # Totals
        total_cost = sum(r['stat_cost'] or 0 for r in rows)
        total_show = sum(r['show_cnt'] or 0 for r in rows)
        total_click = sum(r['click_cnt'] or 0 for r in rows)
        total_clue = sum(r['clue_message_count'] or 0 for r in rows)
        total_consult = sum(r['message_action_cnt'] or 0 for r in rows)
        ctr_avg = round(total_click / total_show * 100, 2) if total_show > 0 else 0
        cpa = round(total_cost / total_clue, 2) if total_clue > 0 else 0
        
        lines = [
            f"🎬 **素材详情**",
            "",
            f"| 字段 | 值 |",
            f"|------|-----|",
            f"| 素材ID | `{first['material_id']}` |",
            f"| 素材名称 | {first['material_name'] or '--'} |",
            f"| 素材类型 | {first['material_type'] or '--'} |",
            f"| 账户ID | `{first['account_id']}` |",
            f"| 数据天数 | {len(rows)}天 |",
            f"| 总消耗 | ¥{total_cost:,.2f} |",
            f"| 总展示 | {total_show:,} |",
            f"| 总点击 | {total_click:,} |",
            f"| CTR | {ctr_avg:.2f}% |",
            f"| 总咨询 | {total_consult} |",
            f"| 总线索 | {total_clue} |",
            f"| CPA | ¥{cpa:,.2f}" if cpa > 0 else f"| CPA | -- |",
            "",
            f"**每日明细**",
            "",
            f"| 日期 | 消耗 | 展示 | 点击 | CTR | 线索 |",
            f"|------|------|------|------|------|------|",
        ]
        for r in rows:
            lines.append(
                f"| {r['stat_date']} | ¥{r['stat_cost'] or 0:,.0f} | "
                f"{r['show_cnt'] or 0:,} | {r['click_cnt'] or 0} | "
                f"{r['ctr'] or 0:.1f}% | {r['clue_message_count'] or 0} |"
            )
        
        conn.close()
        return "\n".join(lines)

    def _material_overview(self) -> str:
        """Generate material performance overview for today."""
        from datetime import date
        today = date.today()
        try:
            from src.pipeline.storage import Storage
            s = Storage()
            latest_date = s.get_latest_date("material_reports")
            if not latest_date:
                return "📊 暂无素材数据，请先同步数据。"
        except Exception:
            latest_date = today.strftime("%Y-%m-%d")
        
        materials = self.material.storage.get_material_summary(latest_date)
        if not materials:
            return f"📊 {latest_date} 暂无素材数据。"
        
        # Sort by cost
        sorted_mats = sorted(materials, key=lambda m: m.get("total_cost", 0) or 0, reverse=True)
        
        total_cost = sum(m.get("total_cost", 0) or 0 for m in materials)
        total_clue = sum(m.get("total_clue", 0) or 0 for m in materials)
        total_consult = sum(m.get("total_consult", 0) or 0 for m in materials)
        
        # Distribution
        type_dist = {}
        for m in materials:
            mt = m.get("material_type", "未知")
            type_dist[mt] = type_dist.get(mt, 0) + 1
        
        lines = [
            f"📊 **素材概览 — {latest_date}**",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 素材总数 | {len(materials)} |",
            f"| 总消耗 | ¥{total_cost:,.0f} |",
            f"| 总咨询 | {total_consult} |",
            f"| 总线索 | {total_clue} |",
            f"| CPA | ¥{total_cost/total_clue:,.0f}" if total_clue > 0 else "| CPA | -- |",
            "",
            f"**素材类型分布**",
            "",
        ]
        for mt, cnt in sorted(type_dist.items(), key=lambda x: -x[1]):
            lines.append(f"- {mt}: {cnt}个")
        
        lines.append("")
        lines.append(f"**消耗 Top 10 素材**")
        lines.append("")
        lines.append(f"| # | 素材名称 | 消耗 | 展示 | 线索 | CTR |")
        lines.append(f"|---|----------|------|------|------|------|")
        for i, m in enumerate(sorted_mats[:10], 1):
            name = (m.get("material_name") or "?")[:25]
            lines.append(
                f"| {i} | {name} | ¥{m.get('total_cost',0) or 0:,.0f} | "
                f"{m.get('total_show',0) or 0:,} | {m.get('total_clue',0) or 0} | "
                f"{m.get('ctr',0) or 0:.1f}% |"
            )
        
        lines.append("")
        lines.append(f"💡 输入 **素材ID <id>** 查看详情，**素材疲劳** 查看衰退素材")
        return "\n".join(lines)

    def _material_fatigue_report(self) -> str:
        """Report materials showing fatigue."""
        fatigued = self.material.detect_material_fatigue(days=14)
        if not fatigued:
            return "✅ 近14天未检测到素材疲劳（CTR无明显衰退）。"
        
        lines = [
            "📉 **素材疲劳检测 (14天CTR衰退>50%)**",
            "",
            f"| 素材 | 账户 | 近期CTR | 峰值CTR | 衰退 | 14天消耗 |",
            f"|------|------|---------|----------|------|----------|",
        ]
        for f in fatigued[:10]:
            name = (f.get("material_name") or "?")[:20]
            acct = (f.get("account_name") or f.get("account_id", "")[-8:])
            lines.append(
                f"| {name} | {acct} | {f['recent_ctr']:.1f}% | "
                f"{f['peak_ctr']:.1f}% | {f['degradation_pct']:.0f}% | "
                f"¥{f['total_cost_14d']:,.0f} |"
            )
        
        lines.append("")
        lines.append(f"💡 建议：对衰退素材**更换文案或视频**，或**暂停观察**")
        return "\n".join(lines)

    def _handle_material_ranking_query(self, text: str) -> str:
        """Handle material ranking queries like '哪个素材CPA最低'."""
        # Determine metric
        if "cpa" in text.lower():
            metric = "cpa"
            metric_name = "CPA"
        elif "留资" in text or "线索" in text:
            metric = "clue"
            metric_name = "留资"
        elif "咨询" in text:
            metric = "consult"
            metric_name = "咨询"
        elif "点击" in text:
            metric = "click"
            metric_name = "点击"
        elif "ctr" in text.lower():
            metric = "ctr"
            metric_name = "CTR"
        else:
            metric = "cost"
            metric_name = "消耗"
        
        from datetime import date
        try:
            from src.pipeline.storage import Storage
            s = Storage()
            latest_date = s.get_latest_date("material_reports")
            if not latest_date:
                return "暂无数据。"
        except Exception:
            latest_date = date.today().strftime("%Y-%m-%d")
        
        materials = self.material.storage.get_material_summary(latest_date)
        if not materials:
            return f"📊 {latest_date} 暂无素材数据。"
        
        # Filter: only materials with meaningful data
        mats = [m for m in materials if (m.get("total_cost", 0) or 0) > 10]
        
        if metric == "cpa":
            # Only materials with clues
            mats = [m for m in mats if (m.get("total_clue", 0) or 0) > 0]
            mats.sort(key=lambda m: (m.get("total_cost", 0) or 0) / (m.get("total_clue", 1)))
            lines = [f"📊 **素材 CPA 排行榜 (消耗>¥10且有留资) — {latest_date}**"]
        elif metric in ("clue", "consult"):
            mats.sort(key=lambda m: m.get(f"total_{metric}", 0) or 0, reverse=True)
            lines = [f"📊 **素材 {metric_name} 排行榜 — {latest_date}**"]
        elif metric == "ctr":
            mats = [m for m in mats if (m.get("total_show", 0) or 0) > 100]
            mats.sort(key=lambda m: m.get("ctr", 0) or 0, reverse=True)
            lines = [f"📊 **素材 CTR 排行榜 (展示>100) — {latest_date}**"]
        else:
            mats.sort(key=lambda m: m.get("total_cost", 0) or 0, reverse=True)
            lines = [f"📊 **素材消耗排行榜 — {latest_date}**"]
        
        lines.extend(["", f"| # | 素材名称 | 消耗 | 展示 | 线索 | CTR | CPA |",
                        f"|---|----------|------|------|------|------|------|"])
        
        for i, m in enumerate(mats[:15], 1):
            name = (m.get("material_name") or "?")[:20]
            cost = m.get("total_cost", 0) or 0
            clue = m.get("total_clue", 0) or 0
            cpa = round(cost / clue, 0) if clue > 0 else 0
            lines.append(
                f"| {i} | {name} | ¥{cost:,.0f} | "
                f"{m.get('total_show',0) or 0:,} | {clue} | "
                f"{m.get('ctr',0) or 0:.1f}% | ¥{cpa:,.0f} |"
            )
        
        lines.append("")
        lines.append(f"💡 点击素材行查看详情：在 **看板 Tab3 素材全榜** 中点击任意素材")
        return "\n".join(lines)

    # ── Reports ────────────────────────────────────────────────

    def generate_daily_report(self, target_date: Optional[date] = None) -> str:
        """Generate a Markdown daily report."""
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        date_str = target_date.strftime("%Y-%m-%d")

        summary = self.kpi.daily_summary(target_date)
        anomalies = self.anomaly.detect_all(target_date)
        ranking = self.kpi.account_ranking(top_n=5)
        suggestions = self.optimizer.generate_suggestions()

        if not summary.get("total_cost"):
            return f"# 📊 日报 - {date_str}\n\n暂无数据。"

        lines = [
            f"# 📊 本地推投放日报",
            f"**日期**: {date_str}",
            "",
            "## 📈 核心指标",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 💰 消耗 | ¥{summary.get('total_cost', 0):,.0f} |",
            f"| 👁 展示 | {summary.get('total_show', 0):,} |",
            f"| 👆 点击 | {summary.get('total_click', 0):,} |",
            f"| ✅ 转化 | {summary.get('total_convert', 0):,} |",
            f"| 💬 咨询 | {summary.get('total_consult', 0):,} |",
            f"| 📋 留资 | {summary.get('total_clue', 0):,} |",
            f"| 📊 CTR | {summary.get('ctr', 0):.2f}% |",
            f"| 📊 CVR | {summary.get('cvr', 0):.2f}% |",
            f"| 💵 CPA | ¥{summary.get('cpa', 0):.2f} |",
            f"| 🏢 活跃账户 | {summary.get('account_count', 0)} |",
            "",
        ]

        if anomalies:
            lines.append("## 🚨 异常告警")
            lines.append("")
            for a in anomalies[:5]:
                sev = "🔴" if a.get("severity") == "high" else "🟡"
                lines.append(f"- {sev} {a['detail']}")
            lines.append("")

        if ranking:
            lines.append("## 🏆 消耗 Top 5 账户")
            lines.append("")
            lines.append("| 排名 | 账户 | 消耗 | 咨询 | 留资 |")
            lines.append("|------|------|------|------|------|")
            for i, r in enumerate(ranking[:5], 1):
                name = r.get("account_name") or r["account_id"][-8:]
                lines.append(
                    f"| {i} | {name} | ¥{r.get('total_cost',0):,.0f} | "
                    f"{r.get('total_consult',0)} | {r.get('total_clue',0)} |"
                )
            lines.append("")

        if suggestions:
            lines.append("## 💡 优化建议")
            lines.append("")
            for s in suggestions[:5]:
                lines.append(f"- **{s['type']}**: {s.get('action', '')} ({s.get('reason', '')})")
            lines.append("")

        lines.append("---")
        lines.append("*由本地推分析 Agent 自动生成*")
        return "\n".join(lines)

    def generate_weekly_report(self) -> str:
        """Generate a Markdown weekly report."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=6)
        prev_start = start - timedelta(days=7)
        prev_end = start - timedelta(days=1)

        comparison = self.kpi.compare_periods(start, end, prev_start, prev_end)
        current = comparison.get("current_period", {})
        previous = comparison.get("previous_period", {})
        changes = comparison.get("changes", {})
        anomalies = self.anomaly.detect_all()
        suggestions = self.optimizer.generate_suggestions()

        def arrow(pct):
            if pct is None:
                return "—"
            if pct == float("inf"):
                return "🆕"
            return f"🔺{pct:.1f}%" if pct > 0 else f"🔻{abs(pct):.1f}%"

        lines = [
            f"# 📊 本地推投放周报",
            f"**周期**: {start} ~ {end}",
            "",
            "## 📈 本周概览",
            "",
            f"| 指标 | 本周 | 上周 | 环比 |",
            f"|------|------|------|------|",
            f"| 💰 消耗 | ¥{current.get('total_cost',0):,.0f} | ¥{previous.get('total_cost',0):,.0f} | {arrow(changes.get('cost_pct'))} |",
            f"| 👁 展示 | {current.get('total_show',0):,} | {previous.get('total_show',0):,} | {arrow(changes.get('show_pct'))} |",
            f"| 💬 咨询 | {current.get('total_consult',0):,} | {previous.get('total_consult',0):,} | {arrow(changes.get('consult_pct'))} |",
            f"| 📋 留资 | {current.get('total_clue',0):,} | {previous.get('total_clue',0):,} | {arrow(changes.get('clue_pct'))} |",
            f"| 📊 CTR | {current.get('ctr',0):.2f}% | {previous.get('ctr',0):.2f}% | — |",
            f"| 💵 CPA | ¥{current.get('cpa',0):.2f} | ¥{previous.get('cpa',0):.2f} | — |",
            "",
        ]

        if anomalies:
            lines.append("## 🚨 异常汇总")
            lines.append("")
            for a in anomalies[:5]:
                sev = "🔴" if a.get("severity") == "high" else "🟡"
                lines.append(f"- {sev} {a['detail']}")
            lines.append("")

        if suggestions:
            lines.append("## 💡 优化建议")
            lines.append("")
            for s in suggestions[:5]:
                lines.append(f"- **{s['type']}**: {s.get('action', '')}")
            lines.append("")

        lines.append("---")
        lines.append("*由本地推分析 Agent 自动生成*")
        return "\n".join(lines)

    # ── Alert Push ─────────────────────────────────────────────

    def push_alerts(self) -> dict:
        """Run anomaly detection + optimization, push alerts to configured channels.

        Returns a summary dict with counts and push statuses.
        """
        anomalies = self.anomaly.detect_all()
        suggestions = self.optimizer.generate_suggestions()

        result = {
            "anomaly_count": len(anomalies),
            "suggestion_count": len(suggestions),
            "channels": {},
            "anomaly_summary": [],
            "suggestion_summary": [],
        }

        # Build alert messages
        lines = ["🚨 **本地推智能告警**", ""]

        if anomalies:
            lines.append(f"## 异常告警 ({len(anomalies)}条)")
            for a in anomalies[:5]:
                sev = "🔴" if a.get("severity") == "high" else "🟡"
                lines.append(f"- {sev} {a.get('type')}: {a.get('detail')}")
            result["anomaly_summary"] = [
                {"type": a["type"], "detail": a.get("detail", "")}
                for a in anomalies[:5]
            ]
        else:
            lines.append("✅ 未检测到异常")

        lines.append("")

        if suggestions:
            high_priority = [s for s in suggestions if s.get("priority") == "high"]
            lines.append(f"## 优化建议 ({len(suggestions)}条, 其中高优{len(high_priority)}条)")
            for s in suggestions[:5]:
                p = "🔴" if s.get("priority") == "high" else "🟡"
                lines.append(f"- {p} {s.get('type')}: {s.get('action', '')}")
            result["suggestion_summary"] = [
                {"type": s["type"], "priority": s.get("priority", ""),
                 "action": s.get("action", "")}
                for s in suggestions[:5]
            ]
        else:
            lines.append("✅ 当前无需优化")

        text = "\n".join(lines)

        # Push to WeChat Work (企业微信)
        if WECOM_WEBHOOK_URL:
            try:
                self._send_wecom(text)
                result["channels"]["wecom"] = "ok"
                logger.info("Alert pushed to WeCom")
            except Exception as e:
                result["channels"]["wecom"] = f"failed: {e}"
                logger.warning("WeCom push failed: %s", e)

        # Push to Feishu (飞书)
        if FEISHU_WEBHOOK_URL:
            try:
                self._send_feishu(text)
                result["channels"]["feishu"] = "ok"
                logger.info("Alert pushed to Feishu")
            except Exception as e:
                result["channels"]["feishu"] = f"failed: {e}"
                logger.warning("Feishu push failed: %s", e)

        if not result["channels"]:
            logger.info("No alert channels configured, alerts generated locally only")

        return result

    def _send_wecom(self, text: str):
        """Send Markdown message to WeChat Work webhook."""
        payload = json.dumps({
            "msgtype": "markdown",
            "markdown": {"content": text},
        }).encode("utf-8")
        req = urllib.request.Request(
            WECOM_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)

    def _send_feishu(self, text: str):
        """Send interactive card message to Feishu webhook."""
        payload = json.dumps({
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "本地推智能告警"},
                    "template": "red",
                },
                "elements": [
                    {"tag": "markdown", "content": text},
                ],
            },
        }).encode("utf-8")
        req = urllib.request.Request(
            FEISHU_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
