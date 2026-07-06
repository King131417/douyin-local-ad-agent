"""
Material Investment Decision Engine

四象限决策框架 + 效率分 + 可执行建议

核心逻辑:
- 按账户内相对排名（避免大账户/小账户不公平）
- 效率分 = 转化成本分位 × 0.4 + 留资率分位 × 0.3 + CTR分位 × 0.15 + 趋势分 × 0.15
- 五类动作: 放量 / 维持 / 观察 / 暂停 / 放弃
- 新增陷阱标记: "便宜但留资差"的素材禁止进入放量清单
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from src.pipeline.storage import Storage

logger = logging.getLogger(__name__)


class MaterialDecisionEngine:
    """素材投资决策引擎 — 四象限分类 + 效率评分 + 行动建议"""

    def __init__(self, storage: Optional[Storage] = None):
        self.storage = storage or Storage()

    # ── Public API ──────────────────────────────────────────

    def analyze(
        self,
        date_str: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """
        全量决策分析 — 看板数据源。

        Returns:
            {
                date, quadrant_summary,  {stars/potential/watch/stop: {count, cost, materials}}
                decision_matrix: scatter data for chart,
                scale_up_candidates: top 10,
                pause_candidates: top 10,
                accounts: per-account breakdown,
                suggestions: natural-language recommendations,
                project_list: 项目列表辅助信息
            }
        """
        # Determine which date mode
        if start_date and end_date:
            date_label = f"{start_date} ~ {end_date}"
            single_date = None
        else:
            if date_str is None:
                date_str = self.storage.get_latest_date("material_reports") or (
                    date.today() - timedelta(days=1)
                ).strftime("%Y-%m-%d")
            date_label = date_str
            single_date = date_str

        # Step1: 捋取原始数据
        raw_materials = self.storage.get_material_summary(
            date_str=single_date,
            start_date=start_date,
            end_date=end_date,
        )
        if not raw_materials:
            return self._empty_result(date_label)

        # Step 2: 计算全局指标 + 账户分组
        account_groups: dict[str, list[dict]] = defaultdict(list)
        for m in raw_materials:
            m = dict(m)
            m["total_cost"] = m.get("total_cost", 0) or 0
            m["total_show"] = m.get("total_show", 0) or 0
            m["total_click"] = m.get("total_click", 0) or 0
            m["total_convert"] = m.get("total_convert", 0) or 0
            m["total_consult"] = m.get("total_consult", 0) or 0
            m["total_clue"] = m.get("total_clue", 0) or 0
            m["ctr"] = m.get("ctr", 0) or 0
            m["cpa"] = m.get("cpa", 0) or 0
            m["lead_cpa"] = m.get("lead_cpa", 0) or 0
            m["lead_cpa"] = round(m["total_cost"] / m["total_clue"], 2) if m["total_clue"] > 0 else 0

            # 留资率 = 留资数 ÷ 咨询(message_action_cnt) — 核心口径
            if m["total_consult"] > 0:
                m["lead_rate"] = round(m["total_clue"] / m["total_consult"] * 100, 2)
            else:
                m["lead_rate"] = 0

            # 咨询率
            if m["total_click"] > 0:
                m["consult_rate"] = round(m["total_consult"] / m["total_click"] * 100, 2)
            else:
                m["consult_rate"] = 0

            # 总转化 = 咨询 + 留资（非重复，但咨询和留资一般是不同人）
            m["total_action"] = m["total_consult"] + m["total_clue"]

            account_groups[m.get("account_id", "unknown")].append(m)

        # Step 3: 每个账户内独立打分 + 分类
        all_scored = []
        for aid, materials in account_groups.items():
            scored = self._score_account_materials(aid, materials)
            all_scored.extend(scored)

        # Step 4: 象限汇总
        quadrant = self._quadrant_summary(all_scored)

        # Step 5: 候选清单
        scale_up = [m for m in all_scored if m["action"] == "scale_up"]
        scale_up.sort(key=lambda m: -m["efficiency_score"])
        scale_up = scale_up[:10]

        pause = [m for m in all_scored if m["action"] in ("pause", "abandon")]
        pause.sort(key=lambda m: -m["total_cost"])
        pause = pause[:10]

        # Step 6: 按账户汇总
        account_summaries = self._account_summaries(account_groups, all_scored)

        # Step 7: 生成建议
        suggestions = self._generate_suggestions(quadrant, scale_up, pause)

        # Step 8: 散点图数据
        scatter = self._build_scatter_data(all_scored)

        # 项目列表辅助信息
        project_list = self._get_project_list()

        return {
            "date": date_label,
            "total_materials": len(all_scored),
            "quadrant_summary": quadrant,
            "decision_matrix": scatter,
            "scale_up_candidates": scale_up,
            "pause_candidates": pause,
            "accounts": account_summaries,
            "suggestions": suggestions,
            "project_list": project_list,
        }

    def get_account_detail(
        self,
        account_id: str,
        date_str: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """单账户穿透分析"""
        if start_date and end_date:
            sd, ed = start_date, end_date
        else:
            if date_str is None:
                date_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
            sd, ed = date_str, date_str

        raw = self.storage.get_material_reports(
            account_id=account_id,
            start_date=sd,
            end_date=ed,
            limit=2000,
        )

        if not raw:
            return {"account_id": account_id, "materials": [], "quadrant": {}}

        # Aggregate by material_id
        mat_map: dict[str, dict] = {}
        for r in raw:
            r = dict(r)
            mid = r["material_id"]
            if mid not in mat_map:
                mat_map[mid] = {
                    "material_id": mid,
                    "material_name": r.get("material_name", ""),
                    "material_type": r.get("material_type", ""),
                    "account_id": r.get("account_id", account_id),
                    "promotion_id": r.get("promotion_id") or "",
                    "promotion_name": r.get("promotion_name") or "",
                    "project_id": r.get("project_id") or "",
                    "project_name": r.get("project_name") or "",
                    "total_cost": 0, "total_show": 0, "total_click": 0,
                    "total_convert": 0, "total_consult": 0, "total_clue": 0,
                }
            m = mat_map[mid]
            m["total_cost"] += r.get("stat_cost", 0) or 0
            m["total_show"] += r.get("show_cnt", 0) or 0
            m["total_click"] += r.get("click_cnt", 0) or 0
            m["total_convert"] += r.get("convert_cnt", 0) or 0
            m["total_consult"] += r.get("message_action_cnt", 0) or 0
            m["total_clue"] += r.get("clue_message_count", 0) or 0
            # Prefer first non-empty attribution name
            if not m["promotion_name"] and r.get("promotion_name"):
                m["promotion_name"] = r["promotion_name"]
            if not m["project_name"] and r.get("project_name"):
                m["project_name"] = r["project_name"]
            if not m["promotion_id"] and r.get("promotion_id"):
                m["promotion_id"] = r["promotion_id"]
            if not m["project_id"] and r.get("project_id"):
                m["project_id"] = r["project_id"]

        materials = list(mat_map.values())
        for m in materials:
            # 留资率 = 留资 ÷ 咨询 — 核心口径
            if m["total_consult"] > 0:
                m["lead_rate"] = round(m["total_clue"] / m["total_consult"] * 100, 2)
            else:
                m["lead_rate"] = 0
            m["ctr"] = round(m["total_click"] / m["total_show"] * 100, 2) if m["total_show"] > 0 else 0
            m["cpa"] = round(m["total_cost"] / m["total_convert"], 2) if m["total_convert"] > 0 else 0      # 转化CPA(参考)
            m["lead_cpa"] = round(m["total_cost"] / m["total_clue"], 2) if m["total_clue"] > 0 else 0       # 转化成本(主指标)
            m["total_action"] = m["total_consult"] + m["total_clue"]

        scored = self._score_account_materials(account_id, materials)
        quadrant = self._quadrant_summary(scored)

        return {
            "account_id": account_id,
            "account_name": scored[0].get("account_name", "") if scored else "",
            "total_cost": sum(m["total_cost"] for m in scored),
            "total_materials": len(scored),
            "quadrant": quadrant,
            "materials": sorted(scored, key=lambda m: -m["efficiency_score"]),
        }

    def get_full_ranking(
        self,
        date_str: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """全局素材排行榜（含所有指标 + 建议）"""
        raw = self.storage.get_material_summary(
            date_str=date_str,
            start_date=start_date,
            end_date=end_date,
        )
        if not raw:
            return []

        account_groups: dict[str, list[dict]] = defaultdict(list)
        for m in raw:
            m = dict(m)
            m["total_cost"] = m.get("total_cost", 0) or 0
            m["total_show"] = m.get("total_show", 0) or 0
            m["total_click"] = m.get("total_click", 0) or 0
            m["total_convert"] = m.get("total_convert", 0) or 0
            m["total_consult"] = m.get("total_consult", 0) or 0
            m["total_clue"] = m.get("total_clue", 0) or 0
            m["ctr"] = m.get("ctr", 0) or 0
            m["cpa"] = m.get("cpa", 0) or 0
            m["lead_cpa"] = m.get("lead_cpa", 0) or 0
            # 留资率 = 留资 ÷ 咨询 — 核心口径
            if m["total_consult"] > 0:
                m["lead_rate"] = round(m["total_clue"] / m["total_consult"] * 100, 2)
            else:
                m["lead_rate"] = 0
            m["total_action"] = m["total_consult"] + m["total_clue"]
            account_groups[m.get("account_id", "unknown")].append(m)

        all_scored = []
        for aid, materials in account_groups.items():
            scored = self._score_account_materials(aid, materials)
            all_scored.extend(scored)

        all_scored.sort(key=lambda m: -m["efficiency_score"])
        return all_scored

    # ── Internal Scoring Logic ─────────────────────────────

    def _score_account_materials(self, account_id: str, materials: list[dict]) -> list[dict]:
        """账户内独立打分系统（转化成本口径）"""
        if not materials:
            return []

        has_data = [m for m in materials if m["total_cost"] >= 10]
        if not has_data:
            has_data = materials

        # ── 提取指标数组 ──
        ctrs = [m["ctr"] for m in has_data]
        lead_rates = [m["lead_rate"] for m in has_data]
        costs = [m["total_cost"] for m in has_data]
        lead_cpas = [m.get("lead_cpa", 0) for m in has_data if m.get("lead_cpa", 0) > 0]
        conv_cpas = [m.get("cpa", 0) for m in has_data if m.get("cpa", 0) > 0]

        # ── 账户内中位数（用于象限判定）──
        lead_cpa_median = self._percentile(sorted(lead_cpas), 50) if lead_cpas else 9999
        cost_median = self._percentile(sorted(costs), 50)
        lead_rate_median = self._percentile(sorted(lead_rates), 50)
        ctr_median = self._percentile(sorted(ctrs), 50)

        # ── 账户级大盘基准（用于陷阱检测）──
        total_consult = sum(m["total_consult"] for m in has_data)
        total_clue = sum(m["total_clue"] for m in has_data)
        bench_consult_cpa = sum(m["total_cost"] for m in has_data) / total_consult if total_consult > 0 else 0
        bench_lead_cpa = sum(m["total_cost"] for m in has_data) / total_clue if total_clue > 0 else 0

        for m in materials:
            # ── 补充转化成本 ──
            if "lead_cpa" not in m:
                m["lead_cpa"] = round(m["total_cost"] / m["total_clue"], 2) if m["total_clue"] > 0 else 0
            lcpa = m["lead_cpa"]

            # ── 留资率(留资/咨询) — 陷阱探测核心口径 ──
            consult_cpa = (m["total_cost"] / m["total_consult"]) if m["total_consult"] > 0 else 0
            lead_conv_rate = (m["total_clue"] / m["total_consult"] * 100) if m["total_consult"] > 0 else 0

            # ── 百分位评分（转化成本 越低越好）──
            pct_lead_cpa = self._rank_pct_inv(m.get("lead_cpa", 9999), lead_cpas + [0])
            pct_lead = self._rank_pct(m["lead_rate"], lead_rates)
            pct_ctr = self._rank_pct(m["ctr"], ctrs)

            # ── 效率分 (0-100)：转化成本权重最高 ──
            m["efficiency_score"] = round(
                (pct_lead_cpa * 0.40 + pct_lead * 0.30 + pct_ctr * 0.15 + 0.5 * 0.15) * 100, 1
            )

            m["ctr_pct"] = round(pct_ctr * 100, 1)
            m["lead_pct"] = round(pct_lead * 100, 1)
            m["lead_cpa_pct"] = round(pct_lead_cpa * 100, 1)

            # ── "便宜但留资差"陷阱检测（咨询成本低但留资率<50%）──
            is_trap = (
                m["total_cost"] >= 10
                and consult_cpa > 0 and bench_consult_cpa > 0
                and consult_cpa <= bench_consult_cpa * 0.9
                and 0 < lead_conv_rate < 50
            )
            m["is_trap"] = is_trap
            m["lead_conv_rate"] = round(lead_conv_rate, 1)
            m["consult_cpa"] = round(consult_cpa, 1)

            # ── 四象限分类（转化成本效率 × 消耗量级）──
            if m["total_cost"] < 10:
                m["quadrant"] = "insufficient"
                m["action"] = "watch"
            elif m["total_clue"] == 0 and m["total_cost"] > 50:
                m["quadrant"] = "stop"
                m["action"] = "abandon"
            else:
                lead_good = lcpa > 0 and lcpa <= lead_cpa_median  # 转化成本优于账户中位数
                cost_big = m["total_cost"] >= cost_median          # 消耗量级高于中位数

                if is_trap:
                    # 陷阱素材：禁止放量，标为"优化留资链路"
                    m["quadrant"] = "stop"
                    m["action"] = "optimize_lead"
                elif lead_good and cost_big:
                    m["quadrant"] = "star"
                    m["action"] = "scale_up"       # 放量
                elif lead_good and not cost_big:
                    m["quadrant"] = "potential"
                    m["action"] = "maintain"        # 小而美，维持观察
                elif not lead_good and cost_big:
                    m["quadrant"] = "stop"
                    m["action"] = "pause"           # 高耗低效，暂停
                else:
                    # lead not good + low cost
                    if m["total_clue"] > 0:
                        m["quadrant"] = "watch"
                        m["action"] = "watch"
                    else:
                        m["quadrant"] = "stop"
                        m["action"] = "abandon" if m["total_cost"] > 50 else "watch"

            # ── 赋标签 ──
            action_labels = {
                "scale_up": "放量",
                "maintain": "维持",
                "watch": "观察",
                "pause": "暂停",
                "abandon": "放弃",
                "optimize_lead": "优化留资链路",
            }
            quadrant_labels = {
                "star": "明星(放量)",
                "potential": "潜力(小而美)",
                "watch": "观察",
                "stop": "淘汰/陷阱",
                "insufficient": "数据不足",
            }
            m["action_label"] = action_labels.get(m["action"], m["action"])
            m["quadrant_label"] = quadrant_labels.get(m["quadrant"], m["quadrant"])

        return materials

    @staticmethod
    def _rank_pct(value: float, all_values: list[float]) -> float:
        """计算 value 在 all_values 中的百分位 (0~1)"""
        if not all_values or max(all_values) == min(all_values):
            return 0.5
        count_below = sum(1 for v in all_values if v < value)
        return count_below / len(all_values)

    @staticmethod
    def _rank_pct_inv(value: float, all_values: list[float]) -> float:
        """反百分位：越低越好（CPA类指标用），value越小排名越高"""
        if not all_values or max(all_values) == min(all_values):
            return 0.5
        # 过滤掉0值
        valid = [v for v in all_values if v > 0]
        if not valid:
            return 0.5
        count_above = sum(1 for v in valid if v > value)
        return count_above / len(valid)

    @staticmethod
    def _percentile(sorted_values: list[float], pct: float) -> float:
        """计算百分位数"""
        if not sorted_values:
            return 0
        idx = int(len(sorted_values) * pct / 100)
        idx = min(idx, len(sorted_values) - 1)
        return sorted_values[idx]

    # ── Summary Builders ───────────────────────────────────

    def _quadrant_summary(self, materials: list[dict]) -> dict:
        """四象限汇总"""
        result: dict[str, dict] = {
            "star": {"count": 0, "total_cost": 0.0, "label": "明星", "icon": "star"},
            "potential": {"count": 0, "total_cost": 0.0, "label": "潜力", "icon": "potential"},
            "watch": {"count": 0, "total_cost": 0.0, "label": "观察", "icon": "watch"},
            "stop": {"count": 0, "total_cost": 0.0, "label": "淘汰", "icon": "stop"},
            "insufficient": {"count": 0, "total_cost": 0.0, "label": "数据不足", "icon": "insufficient"},
        }
        for m in materials:
            q = m.get("quadrant", "watch")
            if q in result:
                result[q]["count"] += 1
                result[q]["total_cost"] += m.get("total_cost", 0) or 0

        for k in result:
            result[k]["total_cost"] = round(result[k]["total_cost"], 2)

        return result

    def _account_summaries(
        self, account_groups: dict[str, list[dict]], all_scored: list[dict]
    ) -> list[dict]:
        """按账户汇总象限分布"""
        scored_map: dict[str, list[dict]] = defaultdict(list)
        for m in all_scored:
            scored_map[m.get("account_id", "unknown")].append(m)

        summaries = []
        for aid, materials in account_groups.items():
            scored = scored_map.get(aid, [])
            quad = self._quadrant_summary(scored)

            total_cost = sum(m.get("total_cost", 0) or 0 for m in materials)
            total_materials = len(materials)
            total_actions = sum(m.get("total_action", 0) for m in materials)

            # 健康度: 明星比例 + 潜力比例
            star_count = quad.get("star", {}).get("count", 0)
            potential_count = quad.get("potential", {}).get("count", 0)
            stop_count = quad.get("stop", {}).get("count", 0)
            if total_materials > 0:
                health = round((star_count * 2 + potential_count) / total_materials * 100)
                health = min(health, 100)
            else:
                health = 0

            summaries.append({
                "account_id": aid,
                "account_name": materials[0].get("account_name", "") if materials else aid[-8:],
                "total_cost": round(total_cost, 2),
                "material_count": total_materials,
                "total_actions": total_actions,
                "health_score": health,
                "quadrant": quad,
            })

        summaries.sort(key=lambda s: -s["total_cost"])
        return summaries

    def _build_scatter_data(self, materials: list[dict]) -> list[dict]:
        """构建散点图数据（过滤消耗>0的素材，限制数量避免过载）"""
        scatter = []
        for m in materials:
            if m.get("total_cost", 0) <= 0:
                continue
            scatter.append({
                "id": m.get("material_id", ""),
                "name": (m.get("material_name", "") or "")[:30],
                "account": m.get("account_name", "") or m.get("account_id", "")[-8:],
                "account_id": m.get("account_id", ""),
                "x": m.get("lead_cpa", 0),        # 转化成本(主指标) — 越低越好
                "y": m.get("total_cost", 0),       # 消耗
                "r": max(3, min(30, m.get("total_clue", 0) * 2 + 3)),  # 气泡=留资数
                "x2": m.get("cpa", 0),             # 转化CPA(参考)
                "quadrant": m.get("quadrant", "watch"),
                "action": m.get("action", "watch"),
                "efficiency": m.get("efficiency_score", 0),
                "lead_rate": m.get("lead_rate", 0),
                "lead_conv_rate": m.get("lead_conv_rate", 0),
                "is_trap": m.get("is_trap", False),
                "total_click": m.get("total_click", 0),
                "total_consult": m.get("total_consult", 0),
                "total_clue": m.get("total_clue", 0),
            })

        # 按消耗排序，取前 500 避免散点图过密
        scatter.sort(key=lambda s: -s["y"])
        return scatter[:500]

    def _material_item(self, m: dict) -> dict:
        """提取素材的关键字段用于建议展示"""
        return {
            "material_id": m.get("material_id", "") or "",
            "material_name": m.get("material_name", "") or "",
            "account_id": m.get("account_id", "") or "",
            "account_name": m.get("account_name", "") or "",
            "promotion_id": m.get("promotion_id", "") or "",
            "promotion_name": m.get("promotion_name", "") or "",
            "project_id": m.get("project_id", "") or "",
            "project_name": m.get("project_name", "") or "",
            "total_cost": m.get("total_cost", 0) or 0,
            "total_show": m.get("total_show", 0) or 0,
            "total_click": m.get("total_click", 0) or 0,
            "total_clue": m.get("total_clue", 0) or 0,
            "ctr": m.get("ctr", 0) or 0,
            "lead_cpa": m.get("lead_cpa", 0) or 0,
            "consult_cpa": m.get("consult_cpa", 0) or 0,
            "lead_conv_rate": m.get("lead_conv_rate", 0) or 0,
            "is_trap": m.get("is_trap", False),
            "action": m.get("action", ""),
            "efficiency_score": m.get("efficiency_score", 0) or 0,
        }

    def _generate_suggestions(
        self, quadrant: dict, scale_up: list[dict], pause: list[dict]
    ) -> list[dict]:
        """生成逐条可执行 + 量化影响的优化建议（附带素材明细）"""
        suggestions = []

        # ── 明星素材放量建议（转化成本口径）──
        if scale_up:
            top5 = scale_up[:5]
            items = []
            for m in top5:
                lcpa = m.get("lead_cpa", 0)
                clue = m.get("total_clue", 0)
                items.append(f"{m.get('material_name','')[:12]}(转化成本¥{lcpa:.0f}·{clue}留资)")
            total_extra = sum(m.get("total_clue", 0) * 0.25 for m in scale_up[:5])
            suggestions.append({
                "type": "scale_up",
                "title": f"🎯 {len(scale_up)} 条素材建议放量（转化成本优于中位）",
                "body": f"以下素材转化成本低、效率优：{'、'.join(items)}。建议预算提升25~50%，预计多拿~{total_extra:.0f}留资。",
                "priority": "high",
                "quantified": f"+{total_extra:.0f}留资预期",
                "materials": [self._material_item(m) for m in top5],
                "action_items": [
                    "提升预算 25~50%",
                    "增加同一项目的相似素材投放",
                    "监控留资成本，若上涨则回调",
                ],
            })

        # ── 陷阱素材警告 ──
        all_materials = scale_up + pause  # use whatever we have
        traps = [m for m in all_materials if m.get("is_trap")]
        if traps:
            trap_items = []
            for m in traps[:5]:
                lcpa = m.get("lead_cpa", 0)
                consult_cpa = m.get("consult_cpa", 0)
                lcr = m.get("lead_conv_rate", 0)
                trap_items.append(f"{m.get('material_name','')[:12]}(咨询成本¥{consult_cpa:.0f}→转化成本¥{lcpa:.0f}·留资率{lcr:.0f}%)")
            suggestions.append({
                "type": "trap_alert",
                "title": f"🪤 {len(traps)} 条素材为「便宜但留资差」陷阱",
                "body": f"咨询成本低但留资率<50%，真实转化成本偏高。已禁止进入放量清单：{'、'.join(trap_items)}。建议优化留资链路/私信话术。",
                "priority": "high",
                "materials": [self._material_item(m) for m in traps[:5]],
                "action_items": [
                    "检查私信自动回复话术，增加留资引导",
                    "优化落地页表单字段，减少用户放弃率",
                    "若3天内无改善，直接暂停该素材",
                ],
            })

        # ── 淘汰素材暂停建议 ──
        stop_materials = [m for m in pause if m["action"] == "abandon"]
        if stop_materials:
            waste_cost = sum(m.get("total_cost", 0) for m in stop_materials)
            top5 = stop_materials[:5]
            suggestions.append({
                "type": "pause",
                "title": f"⚠️ {len(stop_materials)} 条素材建议立即暂停",
                "body": f"有消耗({waste_cost:.0f}元)但零留资。暂停后可释放预算给明星素材，预计每月省 ¥{waste_cost * 4:.0f}（按周耗推断）。",
                "priority": "high",
                "quantified": f"月省¥{waste_cost * 4:.0f}",
                "materials": [self._material_item(m) for m in top5],
                "action_items": [
                    "立即在后台暂停这些素材",
                    "将释放预算转投「建议放量」清单中的素材",
                    "复盘素材内容，分析为何无留资",
                ],
            })

        # ── 高耗低效素材优化建议 ──
        optimize = [m for m in pause if m["action"] == "pause" and not m.get("is_trap")]
        if optimize:
            total_cost = sum(m.get("total_cost", 0) for m in optimize)
            top5 = optimize[:5]
            suggestions.append({
                "type": "optimize",
                "title": f"💡 {len(optimize)} 条素材转化成本偏高，建议降预算或优化",
                "body": f"合计消耗 ¥{total_cost:.0f}，但转化成本高于账户中位数。建议：①降出价5~10%；②优化落地页留资路径；③若优化后无改善则停止。",
                "priority": "medium",
                "quantified": f"可省 ¥{total_cost * 0.3:.0f}",
                "materials": [self._material_item(m) for m in top5],
                "action_items": [
                    "降低出价 5~10%",
                    "A/B测试落地页，减少留资流失",
                    "3天后若CPA未降，直接暂停",
                ],
            })

        # ── 素材生产方向建议 ──
        star_mats = [m for m in scale_up if m.get("lead_cpa", 0) > 0]
        if star_mats:
            avg_lcpa = sum(m["lead_cpa"] for m in star_mats) / len(star_mats)
            avg_lead = sum(m["total_clue"] for m in star_mats) / max(len(star_mats), 1)
            top3 = star_mats[:3]
            suggestions.append({
                "type": "production",
                "title": "📹 素材生产方向建议",
                "body": f"明星素材平均 转化成本 ¥{avg_lcpa:.0f}、均留资{avg_lead:.0f}个。建议：①提炼高留资素材的创意钩子(开头话术/卖点/信任背书)；②复制达人风格批量生产变体；③保持每周≥5条新素材。",
                "priority": "medium",
                "materials": [self._material_item(m) for m in top3],
                "action_items": [
                    "提炼 TOP3 素材的共性创意钩子",
                    "复制达人风格，每周生产≥5条变体",
                    "新素材上架后跑3天再评估",
                ],
            })

        # ── 全局健康度 ──
        star_count = quadrant.get("star", {}).get("count", 0)
        stop_count = quadrant.get("stop", {}).get("count", 0)
        total = sum(q["count"] for q in quadrant.values())
        if total > 0:
            star_ratio = star_count / total
            if star_ratio < 0.1:
                suggestions.append({
                    "type": "alert",
                    "title": "📊 留资高效素材占比偏低",
                    "body": f"转化成本优于中位数的素材仅占 {star_ratio*100:.0f}%。建议集中资源打造3-5条留资效率高的爆款素材。",
                    "priority": "medium",
                    "action_items": [
                        "暂停低效素材，释放预算",
                        "集中资源测试 3-5 个新创意方向",
                        "参考行业高留资素材的脚本结构",
                    ],
                })

        return suggestions

    def _get_project_list(self) -> list[dict]:
        """获取所有账户的项目列表（辅助参考信息）"""
        # 简化版本：从数据库获取账户名称列表
        # 项目详情在需要时通过 API 动态获取
        accounts = self.storage.get_accounts()
        return [
            {"account_id": a["account_id"], "account_name": a["name"]}
            for a in accounts
        ]

    def _empty_result(self, date_str: str) -> dict:
        return {
            "date": date_str,
            "total_materials": 0,
            "quadrant_summary": {
                "star": {"count": 0, "total_cost": 0, "label": "明星", "icon": "star"},
                "potential": {"count": 0, "total_cost": 0, "label": "潜力", "icon": "potential"},
                "watch": {"count": 0, "total_cost": 0, "label": "观察", "icon": "watch"},
                "stop": {"count": 0, "total_cost": 0, "label": "淘汰", "icon": "stop"},
                "insufficient": {"count": 0, "total_cost": 0, "label": "数据不足", "icon": "insufficient"},
            },
            "decision_matrix": [],
            "scale_up_candidates": [],
            "pause_candidates": [],
            "accounts": [],
            "suggestions": [],
            "project_list": [],
        }
