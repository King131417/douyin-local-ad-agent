"""
投手质量诊断雷达 (Quality Radar)
================================

站在专业投手视角，对 账户 → 项目/广告 → 素材 三级做统一的：
  · 核心KPI（消耗/转化/CPA/线索CPA/CTR/CVR + 深度漏斗）
  · 质量分 (0-100) 与分级 (A/B/C/D)
  · 趋势判定（窗口内前半段 vs 后半段，识别疲劳/回暖）
  · 下一步动作（规则化、可解释：加预算/维持/降预算优化/疲劳换创意/淘汰停/排查）

设计原则：
  - 所有实体都和「大盘基准」比，CPA 越低、CVR/CTR 越高得分越高。
  - 量级门槛（置信度）：转化数太少不轻易下"加预算/淘汰"结论，标记为"数据不足-观察"。
  - 动作规则透明，投手一眼能看懂为什么给这个建议。

注意数据现实：
  - 项目(project) 与 广告(promotion) 在本地推数据中 1:1，这里统称"项目/广告"。
  - 素材表无 promotion 归属字段，故 素材 挂在「账户」下，与项目并列下钻，暂不能并入项目树。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

try:
    from config.settings import DATABASE_PATH as _DEFAULT_DB
except Exception:  # pragma: no cover - 允许脱离工程独立测试
    _DEFAULT_DB = "data/ad_data.db"


# ── 质量分权重 & 阈值 ────────────────────────────────────────
W_CPA, W_CVR, W_CTR, W_TREND = 0.40, 0.30, 0.15, 0.15
GRADE_A, GRADE_B, GRADE_C = 80, 65, 50

# 不同层级的"放心下结论"所需的最小转化量（置信门槛）
MIN_CONV = {"account": 30, "promotion": 8, "material": 6}
# 判定"还在花钱值得管"的最小消耗（窗口内）
MIN_COST = {"account": 200, "promotion": 200, "material": 200}
# 趋势恶化/回暖阈值（后半段CPA / 前半段CPA）
TREND_BAD, TREND_GOOD = 1.30, 0.80


def _cap_ratio(x: float, cap: float = 1.5) -> float:
    """把一个比值压到 [0, cap] 再归一到 [0,1]。"""
    if x <= 0:
        return 0.0
    return min(x, cap) / cap


class QualityRadar:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _DEFAULT_DB

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    # ── 窗口与基准 ────────────────────────────────────────
    def _window(self, conn, days: int):
        latest = conn.execute(
            "SELECT MAX(stat_date) FROM material_reports"
        ).fetchone()[0]
        if not latest:
            return None, None, None
        end = datetime.strptime(latest, "%Y-%m-%d")
        start = end - timedelta(days=days - 1)
        mid = end - timedelta(days=days // 2)  # 前半 / 后半 分界
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), mid.strftime("%Y-%m-%d")

    def _benchmark(self, conn, start, end):
        r = conn.execute(
            """SELECT SUM(stat_cost) c, SUM(convert_cnt) v, SUM(clue_message_count) u,
                      SUM(message_action_cnt) msg, SUM(click_cnt) k, SUM(show_cnt) s
               FROM account_reports WHERE stat_date BETWEEN ? AND ?
               AND delivery_type = 'total'""",
            (start, end),
        ).fetchone()
        cost, conv, clue, consult, clk, shw = (r[0] or 0), (r[1] or 0), (r[2] or 0), (r[3] or 0), (r[4] or 0), (r[5] or 0)
        return {
            "cpa": (cost / clue) if clue else 0.0,             # 转化成本(消耗/留资)
            "lead_cpa": (cost / clue) if clue else 0.0,        # 转化成本(主指标)
            "consult_cpa": (cost / consult) if consult else 0.0, # 咨询成本(消耗/咨询)
            "cvr": (conv / clk) if clk else 0.0,
            "lead_rate": (clue / consult) if consult else 0.0,   # 留资率(留资/咨询)
            "ctr": (clk / shw) if shw else 0.0,
            "cost": cost,
            "convert": conv,
            "clue": clue,
            "consult": consult,
        }

    # ── 评分 + 动作（核心，三级共用）────────────────────────
    def _score_and_action(self, e: dict, bench: dict, level: str) -> dict:
        cost = e["cost"]
        conv = e["conv"]
        clue = e.get("clue", 0)               # 留资/线索数 = 真实业务目标
        consult = e.get("consult", 0) or e.get("msg", 0)  # 咨询数(message_action_cnt)
        ctr = (e["click"] / e["show"]) if e["show"] else 0.0
        consult_cpa = (cost / consult) if consult else 0.0  # 咨询成本(消耗/咨询)
        lead_cpa = (cost / clue) if clue else 0.0           # 转化成本(消耗/留资,主指标)
        lead_rate = (clue / consult) if consult else 0.0     # 留资率(留资/咨询) — 陷阱探测
        lead_per_click = (clue / e["click"]) if e["click"] else 0.0

        # 趋势：以「转化成本」后半段 vs 前半段
        c_old, u_old = e.get("cost_old", 0), e.get("clue_old", 0)
        c_new, u_new = e.get("cost_new", 0), e.get("clue_new", 0)
        lcpa_old = (c_old / u_old) if u_old else 0.0
        lcpa_new = (c_new / u_new) if u_new else 0.0
        if lcpa_old > 0 and lcpa_new > 0:
            tr = lcpa_new / lcpa_old
            if tr >= TREND_BAD:
                trend, trend_score = "deteriorating", 0.2
            elif tr <= TREND_GOOD:
                trend, trend_score = "improving", 1.0
            else:
                trend, trend_score = "stable", 0.6
        else:
            trend, trend_score = "n/a", 0.5

        # 分项得分（CPA项用转化成本；效率项用留资率 留资/点击）
        cpa_score = _cap_ratio(bench["lead_cpa"] / lead_cpa) if lead_cpa else 0.0
        lr_score = _cap_ratio(lead_per_click / bench["lead_rate"]) if bench["lead_rate"] else 0.0
        ctr_score = _cap_ratio(ctr / bench["ctr"]) if bench["ctr"] else 0.0
        score = 100 * (
            W_CPA * cpa_score + W_CVR * lr_score + W_CTR * ctr_score + W_TREND * trend_score
        )
        score = round(score, 1)

        confident = clue >= MIN_CONV[level]   # 以留资量判置信度
        spending = cost >= MIN_COST[level]
        grade = "A" if score >= GRADE_A else "B" if score >= GRADE_B else "C" if score >= GRADE_C else "D"

        # 转化成本 相对大盘的位置（投手第一杠杆）
        bl = bench["lead_cpa"] or 0
        lead_ratio = (lead_cpa / bl) if (bl and lead_cpa) else None  # <1 优于大盘, >1 差于大盘

        # "便宜但留资差"陷阱：咨询成本低但留资率差（私信灌水/搜索智投等）
        trap = (
            consult_cpa > 0 and bench.get("consult_cpa", 0) > 0
            and consult_cpa <= bench["consult_cpa"] * 0.9
            and 0 < lead_rate < 0.5
        )

        # ── 动作规则（按优先级，全部基于留资）──
        if cost <= 0:
            action, reason = "排查", "窗口内0消耗，确认是否主动关停/异常(余额/审核)"
        elif spending and clue == 0:
            action = "淘汰停" if level == "material" else "排查"
            reason = f"消耗¥{cost:.0f}却0留资，{'直接停' if level=='material' else '排查投放/落地链路'}"
        elif trap and spending:
            action = "优化留资链路"
            reason = (f"陷阱：咨询成本¥{consult_cpa:.0f}看着便宜，但留资率仅{lead_rate*100:.0f}%、"
                      f"真实转化成本¥{lead_cpa:.0f}。优化私信话术/引导留资，勿盲目加量")
        elif trend == "deteriorating" and spending:
            action = "疲劳-降预算/换创意"
            reason = f"转化成本恶化{(lcpa_new/lcpa_old-1)*100:.0f}%(¥{lcpa_old:.0f}→¥{lcpa_new:.0f})，先降预算观察"
        elif not confident:
            action, reason = "数据不足-观察", f"留资仅{clue}，样本不足，继续小预算验证"
        elif lead_ratio is not None and lead_ratio <= 0.85 and trend != "deteriorating":
            action = "加预算"
            reason = f"转化成本¥{lead_cpa:.0f}比大盘¥{bl:.0f}低{(1-lead_ratio)*100:.0f}%，效率优，小步加量+20~30%"
        elif lead_ratio is not None and lead_ratio >= 1.20 and spending:
            action = "降预算/优化"
            reason = f"转化成本¥{lead_cpa:.0f}比大盘¥{bl:.0f}高{(lead_ratio-1)*100:.0f}%，压预算或优化定向/创意/出价"
        else:
            action, reason = "维持", f"转化成本¥{lead_cpa:.0f}与大盘¥{bl:.0f}接近，保持预算观察"

        # 素材四象限（消耗量 × 转化成本效率，对标大盘）
        quadrant = None
        if level == "material":
            good = lead_ratio is not None and lead_ratio <= 1.0
            big = cost >= MIN_COST["material"] * 1.5
            if good and big:
                quadrant = "放量(明星)"
            elif good and not big:
                quadrant = "潜力(小而美)"
            elif (not good) and big:
                quadrant = "优化(高耗低效)"
            else:
                quadrant = "观察/淘汰"

        return {
            "cost": round(cost, 0),
            "convert": conv,
            "clue": clue,
            "cpa": round(lead_cpa, 1),           # 转化成本(消耗/留资)
            "consult_cpa": round(consult_cpa, 1), # 咨询成本(消耗/咨询)
            "lead_cpa": round(lead_cpa, 1),      # 转化成本(主)
            "clue_cpa": round(lead_cpa, 1),      # 兼容前端旧字段名
            "lead_rate": round(lead_rate * 100, 0),  # 留资率%(留资/咨询)
            "ctr": round(ctr * 100, 2),
            "cvr": round((conv / e["click"] * 100) if e["click"] else 0, 1),
            "score": score,
            "grade": grade,
            "trend": trend,
            "lead_cpa_old": round(lcpa_old, 1),
            "lead_cpa_new": round(lcpa_new, 1),
            "action": action,
            "reason": reason,
            "trap": trap,
            "quadrant": quadrant,
            "confident": confident,
        }

    # ── 一级：账户 ────────────────────────────────────────
    def accounts(self, days: int = 7,
                 start_date: str | None = None,
                 end_date: str | None = None) -> dict:
        conn = self._conn()
        if start_date and end_date:
            start, end = start_date, end_date
            from datetime import datetime
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            days = (end_dt - start_dt).days + 1
            mid = (start_dt + (end_dt - start_dt) // 2).strftime("%Y-%m-%d")
        else:
            start, end, mid = self._window(conn, days)
        if not start:
            return {"window": None, "benchmark": {}, "rows": []}
        bench = self._benchmark(conn, start, end)
        rows = conn.execute(
            """
            SELECT r.account_id, COALESCE(a.name, r.account_id) name,
              SUM(r.stat_cost) cost, SUM(r.convert_cnt) conv, SUM(r.clue_message_count) clue,
              SUM(r.message_action_cnt) consult, SUM(r.click_cnt) click, SUM(r.show_cnt) show,
              SUM(CASE WHEN r.stat_date < ? THEN r.stat_cost ELSE 0 END) cost_old,
              SUM(CASE WHEN r.stat_date < ? THEN r.convert_cnt ELSE 0 END) conv_old,
              SUM(CASE WHEN r.stat_date < ? THEN r.clue_message_count ELSE 0 END) clue_old,
              SUM(CASE WHEN r.stat_date >= ? THEN r.stat_cost ELSE 0 END) cost_new,
              SUM(CASE WHEN r.stat_date >= ? THEN r.convert_cnt ELSE 0 END) conv_new,
              SUM(CASE WHEN r.stat_date >= ? THEN r.clue_message_count ELSE 0 END) clue_new
            FROM account_reports r LEFT JOIN accounts a ON a.account_id=r.account_id
            WHERE r.stat_date BETWEEN ? AND ?
              AND r.delivery_type = 'total'
            GROUP BY r.account_id
            """,
            (mid, mid, mid, mid, mid, mid, start, end),
        ).fetchall()
        out = []
        for r in rows:
            e = dict(r)
            res = self._score_and_action(e, bench, "account")
            res.update({"account_id": e["account_id"], "name": e["name"]})
            out.append(res)
        out.sort(key=lambda x: x["cost"], reverse=True)
        conn.close()
        return {"window": f"{start} ~ {end}", "days": days, "benchmark": {
            "cpa": round(bench["cpa"], 1),
            "lead_cpa": round(bench["lead_cpa"], 1),
            "cvr": round(bench["cvr"] * 100, 1),
            "lead_rate": round(bench["lead_rate"] * 100, 1),
            "ctr": round(bench["ctr"] * 100, 2), "cost": round(bench["cost"], 0),
            "convert": bench["convert"], "clue": bench["clue"]}, "rows": out}

    # ── 二级：项目/广告（指定账户）─────────────────────────
    def promotions(self, account_id: str, days: int = 7) -> dict:
        conn = self._conn()
        start, end, mid = self._window(conn, days)
        if not start:
            return {"window": None, "rows": []}
        bench = self._benchmark(conn, start, end)
        rows = conn.execute(
            """
            SELECT promotion_id, MAX(promotion_name) name, MAX(project_name) project,
              SUM(stat_cost) cost, SUM(convert_cnt) conv, SUM(clue_message_count) clue,
              SUM(message_action_cnt) consult, SUM(click_cnt) click, SUM(show_cnt) show,
              SUM(CASE WHEN stat_date < ? THEN stat_cost ELSE 0 END) cost_old,
              SUM(CASE WHEN stat_date < ? THEN convert_cnt ELSE 0 END) conv_old,
              SUM(CASE WHEN stat_date < ? THEN clue_message_count ELSE 0 END) clue_old,
              SUM(CASE WHEN stat_date >= ? THEN stat_cost ELSE 0 END) cost_new,
              SUM(CASE WHEN stat_date >= ? THEN convert_cnt ELSE 0 END) conv_new,
              SUM(CASE WHEN stat_date >= ? THEN clue_message_count ELSE 0 END) clue_new
            FROM promotion_reports
            WHERE account_id=? AND stat_date BETWEEN ? AND ?
            GROUP BY promotion_id
            """,
            (mid, mid, mid, mid, mid, mid, account_id, start, end),
        ).fetchall()
        out = []
        for r in rows:
            e = dict(r)
            res = self._score_and_action(e, bench, "promotion")
            res.update({"promotion_id": e["promotion_id"],
                        "name": e["name"] or e["promotion_id"], "project": e["project"]})
            out.append(res)
        out.sort(key=lambda x: x["cost"], reverse=True)
        conn.close()
        return {"window": f"{start} ~ {end}", "days": days, "rows": out}

    # ── 三级：素材（指定账户）+ 深度漏斗 ───────────────────
    def materials(self, account_id: str, days: int = 7) -> dict:
        conn = self._conn()
        start, end, mid = self._window(conn, days)
        if not start:
            return {"window": None, "rows": []}
        bench = self._benchmark(conn, start, end)
        rows = conn.execute(
            """
            SELECT material_id, MAX(material_name) name,
              SUM(stat_cost) cost, SUM(convert_cnt) conv, SUM(clue_message_count) clue,
              SUM(message_action_cnt) msg, SUM(click_cnt) click, SUM(show_cnt) show,
              SUM(CASE WHEN stat_date < ? THEN stat_cost ELSE 0 END) cost_old,
              SUM(CASE WHEN stat_date < ? THEN convert_cnt ELSE 0 END) conv_old,
              SUM(CASE WHEN stat_date < ? THEN clue_message_count ELSE 0 END) clue_old,
              SUM(CASE WHEN stat_date >= ? THEN stat_cost ELSE 0 END) cost_new,
              SUM(CASE WHEN stat_date >= ? THEN convert_cnt ELSE 0 END) conv_new,
              SUM(CASE WHEN stat_date >= ? THEN clue_message_count ELSE 0 END) clue_new,
              GROUP_CONCAT(raw_data, '\x1f') raws
            FROM material_reports
            WHERE account_id=? AND stat_date BETWEEN ? AND ?
            GROUP BY material_id
            """,
            (mid, mid, mid, mid, mid, mid, account_id, start, end),
        ).fetchall()
        out = []
        for r in rows:
            e = dict(r)
            # 深度漏斗：从 raw_data 累加 电话确认/接通/成交
            ph_conf = ph_conn = pay = 0
            if e.get("raws"):
                for raw in e["raws"].split("\x1f"):
                    if not raw:
                        continue
                    try:
                        d = json.loads(raw)
                        ph_conf += int(d.get("phone_confirm_cnt") or 0)
                        ph_conn += int(d.get("phone_connect_cnt") or 0)
                        pay += int(d.get("clue_pay_order_cnt") or 0)
                    except Exception:
                        pass
            res = self._score_and_action(e, bench, "material")
            res.update({
                "material_id": e["material_id"], "name": e["name"] or e["material_id"],
                "msg": e["msg"] or 0, "phone_confirm": ph_conf,
                "phone_connect": ph_conn, "pay": pay,
            })
            out.append(res)
        out.sort(key=lambda x: x["cost"], reverse=True)
        conn.close()
        return {"window": f"{start} ~ {end}", "days": days, "rows": out}

    # ── 每日作战清单（跨账户汇总，五张表）─────────────────────
    def battle_list(self, days: int = 7,
                    start_date: str | None = None,
                    end_date: str | None = None) -> dict:
        """生成可执行作战清单：
           放量/降量(计划级) + 疲劳/陷阱(素材级) + 排查(账户级)，含量化预期。
           支持 start_date/end_date 精确指定窗口；否则按 days 从最新数据回算。"""
        conn = self._conn()
        if start_date and end_date:
            # 用户指定日期范围：直接使用
            start, end = start_date, end_date
            from datetime import datetime
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            days_span = (end_dt - start_dt).days + 1
            mid = (start_dt + (end_dt - start_dt) // 2).strftime("%Y-%m-%d")
            days = days_span
        else:
            start, end, mid = self._window(conn, days)
        if not start:
            return {"window": None}
        bench = self._benchmark(conn, start, end)
        bl = bench["lead_cpa"] or 0

        def split_cols(prefix=""):
            p = prefix
            return (f"SUM(CASE WHEN {p}stat_date < ? THEN {p}stat_cost ELSE 0 END) cost_old,"
                    f"SUM(CASE WHEN {p}stat_date < ? THEN {p}convert_cnt ELSE 0 END) conv_old,"
                    f"SUM(CASE WHEN {p}stat_date < ? THEN {p}clue_message_count ELSE 0 END) clue_old,"
                    f"SUM(CASE WHEN {p}stat_date >= ? THEN {p}stat_cost ELSE 0 END) cost_new,"
                    f"SUM(CASE WHEN {p}stat_date >= ? THEN {p}convert_cnt ELSE 0 END) conv_new,"
                    f"SUM(CASE WHEN {p}stat_date >= ? THEN {p}clue_message_count ELSE 0 END) clue_new")

        # 计划级（跨账户）
        proms = conn.execute(
            f"""SELECT p.account_id, COALESCE(a.name,p.account_id) acc, p.promotion_id,
                  MAX(p.promotion_name) name,
                  SUM(p.stat_cost) cost, SUM(p.convert_cnt) conv, SUM(p.clue_message_count) clue,
                  SUM(p.message_action_cnt) consult, SUM(p.click_cnt) click, SUM(p.show_cnt) show, {split_cols('p.')}
                FROM promotion_reports p LEFT JOIN accounts a ON a.account_id=p.account_id
                WHERE p.stat_date BETWEEN ? AND ?
                GROUP BY p.account_id, p.promotion_id""",
            (mid, mid, mid, mid, mid, mid, start, end),
        ).fetchall()
        prom_scored = []
        for r in proms:
            e = dict(r)
            res = self._score_and_action(e, bench, "promotion")
            res.update({"acc": e["acc"], "name": e["name"] or e["promotion_id"]})
            prom_scored.append(res)

        # 素材级（跨账户，作战清单不需深度漏斗，跳过raw解析以提速）
        mats = conn.execute(
            f"""SELECT m.account_id, COALESCE(a.name,m.account_id) acc, m.material_id,
                  MAX(m.material_name) name,
                  SUM(m.stat_cost) cost, SUM(m.convert_cnt) conv, SUM(m.clue_message_count) clue,
                  SUM(m.message_action_cnt) consult, SUM(m.click_cnt) click, SUM(m.show_cnt) show, {split_cols('m.')}
                FROM material_reports m LEFT JOIN accounts a ON a.account_id=m.account_id
                WHERE m.stat_date BETWEEN ? AND ?
                GROUP BY m.account_id, m.material_id""",
            (mid, mid, mid, mid, mid, mid, start, end),
        ).fetchall()
        mat_scored = []
        for r in mats:
            e = dict(r)
            res = self._score_and_action(e, bench, "material")
            res.update({"acc": e["acc"], "name": e["name"] or e["material_id"]})
            mat_scored.append(res)

        # 账户级（复用 accounts）
        accs = self.accounts(days, start_date=start_date, end_date=end_date)["rows"]
        conn.close()

        def overspend(x):  # 相对大盘多花的钱（估算可省）
            return round(x["cost"] - x["clue"] * bl) if x["clue"] else round(x["cost"])

        def extra_leads(x):  # +25%预算估算多拿留资
            return round(x["clue"] * 0.25)

        # ① 放量(计划)：动作=加预算，按留资量(已验证规模)排序
        scale = [p for p in prom_scored if p["action"] == "加预算"]
        scale.sort(key=lambda x: -x["clue"])
        scale_up = [{**p, "suggest": "+25%预算", "impact": f"约+{extra_leads(p)}留资/{days}天"} for p in scale[:15]]

        # ② 降量(计划)：动作=降预算/优化，按可省金额排序
        cut = [p for p in prom_scored if p["action"] == "降预算/优化"]
        cut.sort(key=lambda x: -overspend(x))
        cut_down = [{**p, "suggest": "压20%或优化", "impact": f"约省¥{overspend(p)}/{days}天"} for p in cut[:15]]

        # ③ 疲劳预警(素材)：转化成本走差，按恶化幅度排序
        fat = [m for m in mat_scored if m["trend"] == "deteriorating" and m["cost"] >= MIN_COST["material"]]
        fat.sort(key=lambda x: -(x["lead_cpa_new"] / x["lead_cpa_old"] if x["lead_cpa_old"] else 0))
        fatigue = [{**m, "impact": f"转化成本 ¥{m['lead_cpa_old']:.0f}→¥{m['lead_cpa_new']:.0f}"} for m in fat[:15]]

        # ④ 陷阱(计划+素材)：便宜但留资差
        trap_p = [{**x, "lvl": "计划"} for x in prom_scored if x.get("trap")]
        trap_m = [{**x, "lvl": "素材"} for x in mat_scored if x.get("trap")]
        traps = trap_p + trap_m
        traps.sort(key=lambda x: -x["cost"])
        traps = traps[:20]

        # ⑤ 排查(账户)：0消耗 或 动作=排查
        check = [{**a, "note": a["reason"]} for a in accs if a["action"] == "排查"]

        return {
            "window": f"{start} ~ {end}", "days": days,
            "benchmark": {"lead_cpa": round(bl, 1), "cpa": round(bench["cpa"], 1),
                          "cost": round(bench["cost"], 0), "clue": bench["clue"]},
            "scale_up": scale_up, "cut_down": cut_down,
            "fatigue": fatigue, "traps": traps, "check": check,
        }


if __name__ == "__main__":
    import os
    r = QualityRadar(os.getenv("AD_DATA_DB"))
    acc = r.accounts(7)
    print("窗口:", acc["window"], "| 大盘基准:", acc["benchmark"])
    print(f"账户数: {len(acc['rows'])}")
    for a in acc["rows"][:5]:
        print(f"  {a['name'][:14]:<15} ¥{a['cost']:>7.0f} CPA{a['cpa']:>5} "
              f"分{a['score']:>5} {a['grade']} {a['trend']:<13} → {a['action']}")
