#!/usr/bin/env python3
"""
抖音本地推投流分析 - 快捷指令

Usage:
  python ad.py 看板              # 启动数据看板 (默认8888端口)
  python ad.py 同步              # 同步今天的数据
  python ad.py 同步 2026-06-25   # 同步指定日期
  python ad.py 回填 7            # 回填最近7天数据
  python ad.py 日报              # 生成今日投流日报
  python ad.py 周报              # 生成本周周报
  python ad.py 告警              # 检查异常并推送告警
  python ad.py 总览              # 全局投流概览 (所有账户汇总)
  python ad.py 排行              # 账户消耗排行
  python ad.py 分析 01成都三老板   # 分析指定账户 (关键词匹配)
  python ad.py 分析 全部          # 逐个分析所有活跃账户
  python ad.py 素材              # 全局素材排名 TOP20
  python ad.py 素材 01成都三老板    # 指定账户素材排名
  python ad.py 素材决策 01成都三老板  # 素材四象限决策分析
  python ad.py 项目 01成都三老板    # 项目级分析 (消耗/转化按项目聚合)
  python ad.py 单元 01成都三老板    # 投放单元级分析
  python ad.py 账户列表           # 列出所有子账户及最新状态
  python ad.py 对账              # 对账检查: 账户总消耗 vs 单元消耗, 检测已删除实体缺口
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

# ── 加载 .env ──────────────────────────────────────────────
def _load_dotenv():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("\"'")
            if key not in os.environ:
                os.environ[key] = val

_load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ad")

DB_PATH = PROJECT_ROOT / "data" / "ad_data.db"


# ── Helpers ────────────────────────────────────────────────

def _get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _latest_date(table="account_reports"):
    conn = _get_conn()
    row = conn.execute(f"SELECT MAX(stat_date) as d FROM {table}").fetchone()
    conn.close()
    return row["d"] if row and row["d"] else date.today().strftime("%Y-%m-%d")


def _resolve_account(keyword):
    """模糊匹配账户名，返回 (account_id, account_name)。
    支持数字编号（如 01, 02）和关键词匹配。
    """
    from config.settings import LOCAL_SUB_ACCOUNTS
    if not keyword or keyword in ("全部", "all", "所有"):
        return None, "全部账户"
    # 先尝试编号精确匹配（如 "01" → 以 "01" 开头的账户）
    if keyword.isdigit() and len(keyword) <= 2:
        matches = [(k, v) for k, v in LOCAL_SUB_ACCOUNTS.items() if k.startswith(keyword)]
        if len(matches) == 1:
            return matches[0][1], matches[0][0]
        if len(matches) > 1:
            print(f"  编号 {keyword} 匹配到多个账户：")
            for k, v in matches:
                print(f"    {k} ({v})")
            sys.exit(1)
    # 关键词模糊匹配
    matches = [(k, v) for k, v in LOCAL_SUB_ACCOUNTS.items() if keyword in k]
    if not matches:
        print(f"  未找到包含 '{keyword}' 的账户，可用账户：")
        for k in LOCAL_SUB_ACCOUNTS:
            print(f"    {k}")
        sys.exit(1)
    if len(matches) > 1:
        print(f"  匹配到多个账户，请更精确（可用编号如 01）：")
        for k, v in matches:
            print(f"    {k} ({v})")
        sys.exit(1)
    return matches[0][1], matches[0][0]


def _fmt_money(v):
    if v is None:
        return "0"
    if v >= 10000:
        return f"{v/10000:.2f}万"
    return f"{v:.0f}"


def _fmt_pct(v):
    if v is None:
        return "-"
    return f"{v:.2f}%"


def _print_table(rows, headers, col_widths=None):
    """简单表格打印。"""
    if not col_widths:
        col_widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0)) + 2
                       for i, h in enumerate(headers)]
    # header
    print("  " + "".join(str(h).ljust(w) for h, w in zip(headers, col_widths)))
    print("  " + "-" * sum(col_widths))
    for row in rows:
        print("  " + "".join(str(row[i]).ljust(w) for i, w in enumerate(col_widths)))


# ── Commands ───────────────────────────────────────────────

def cmd_dashboard(args):
    """启动数据看板"""
    import subprocess, os
    port = args.port if hasattr(args, "port") else 8888
    print(f"启动双驾驶舱看板 http://localhost:{port}")
    print(f"  Tab1: 素材驾驶舱 | Tab2: 投流账户驾驶舱")
    # Auto-detect venv Python (managed Python has flask installed)
    venv_python = os.path.expanduser("~/.workbuddy/binaries/python/envs/default/bin/python3")
    if os.path.exists(venv_python):
        subprocess.Popen([venv_python, "-c",
            "import sys; sys.path.insert(0,'.'); "
            f"from src.web.app import start_dashboard; start_dashboard({port}, debug=False)"],
            cwd=os.path.join(os.path.dirname(os.path.abspath(__file__))))
    else:
        from src.web.app import start_dashboard
        start_dashboard(port=port)


def cmd_sync(args):
    """同步数据"""
    from src.pipeline.etl import ETLPipeline
    pipeline = ETLPipeline()
    if args.date:
        target = date.fromisoformat(args.date)
        count = pipeline.run_daily_sync(target)
        print(f"同步 {args.date} 完成，共 {count} 条")
    else:
        count = pipeline.run_daily_sync()
        print(f"同步今天完成，共 {count} 条")


def cmd_backfill(args):
    """回填数据"""
    from src.pipeline.etl import ETLPipeline
    pipeline = ETLPipeline()
    days = args.days or 7
    count = pipeline.run_backfill(days=days)
    print(f"回填最近 {days} 天完成，共 {count} 条")


def cmd_report(args):
    """生成报告"""
    from src.agent.agent import AdAgent
    agent = AdAgent()
    from config.settings import OUTPUTS_DIR

    if args.type == "周报":
        report = agent.generate_weekly_report()
        filename = f"周报_{date.today().strftime('%Y%m%d')}.md"
    else:
        report = agent.generate_daily_report()
        filename = f"日报_{date.today().strftime('%Y%m%d')}.md"

    filepath = OUTPUTS_DIR / filename
    filepath.write_text(report, encoding="utf-8")
    print(f"报告已保存: {filepath}")
    print(report[:500] + "..." if len(report) > 500 else report)


def cmd_alerts(args):
    """检查告警"""
    from src.agent.agent import AdAgent
    agent = AdAgent()
    agent.push_alerts()
    print("告警检查完成")


def cmd_overview(args):
    """全局投流概览"""
    target_date = _latest_date()
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT
            COUNT(DISTINCT account_id) as accounts,
            SUM(stat_cost) as cost,
            SUM(show_cnt) as shows,
            SUM(click_cnt) as clicks,
            SUM(convert_cnt) as converts,
            SUM(message_action_cnt) as consults,
            SUM(clue_message_count) as clues,
            CASE WHEN SUM(show_cnt)>0 THEN ROUND(SUM(click_cnt)*100.0/SUM(show_cnt),2) END as ctr,
            CASE WHEN SUM(click_cnt)>0 THEN ROUND(SUM(convert_cnt)*100.0/SUM(click_cnt),2) END as cvr,
            CASE WHEN SUM(convert_cnt)>0 THEN ROUND(SUM(stat_cost)/SUM(convert_cnt),2) END as cpa
        FROM account_reports WHERE stat_date = ?
        """,
        (target_date,),
    ).fetchone()
    conn.close()

    if not row or not row["cost"]:
        print(f"  {target_date} 无数据，请先运行: python ad.py 同步")
        return

    print(f"\n  全局投流概览 | {target_date}")
    print(f"  {'─' * 40}")
    print(f"  活跃账户:   {row['accounts']} 个")
    print(f"  总消耗:     ¥{_fmt_money(row['cost'])}")
    print(f"  展示量:     {row['shows']:,}")
    print(f"  点击量:     {row['clicks']:,}")
    print(f"  点击率:     {_fmt_pct(row['ctr'])}")
    print(f"  转化数:     {row['converts']}")
    print(f"  留资数:     {row['clues']}")
    print(f"  转化率:     {_fmt_pct(row['cvr'])}")
    print(f"  转化成本:   ¥{row['cpa'] or 0}")
    print()


def cmd_ranking(args):
    """账户消耗排行"""
    target_date = _latest_date()
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT
            a.name as name,
            r.stat_cost as cost,
            r.show_cnt as shows,
            r.click_cnt as clicks,
            r.convert_cnt as converts,
            r.clue_message_count as clues,
            CASE WHEN r.show_cnt>0 THEN ROUND(r.click_cnt*100.0/r.show_cnt,2) END as ctr,
            CASE WHEN r.convert_cnt>0 THEN ROUND(r.stat_cost/r.convert_cnt,2) END as cpa
        FROM account_reports r
        LEFT JOIN accounts a ON r.account_id = a.account_id
        WHERE r.stat_date = ?
        ORDER BY r.stat_cost DESC
        """,
        (target_date,),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"  {target_date} 无数据")
        return

    print(f"\n  账户消耗排行 | {target_date}")
    print(f"  {'─' * 70}")
    data = []
    for i, r in enumerate(rows, 1):
        data.append([
            f"{i}",
            (r["name"] or "未知")[:16],
            f"¥{_fmt_money(r['cost'])}",
            f"{r['converts']}",
            f"{r['clues']}",
            f"¥{r['cpa'] or 0}",
        ])
    _print_table(data, ["#", "账户", "消耗", "转化", "留资", "CPA"])
    print()


def cmd_analyze(args):
    """分析指定账户"""
    account_id, account_name = _resolve_account(args.keyword)

    if account_id is None:
        # 全部账户
        from config.settings import LOCAL_SUB_ACCOUNTS
        for name, aid in LOCAL_SUB_ACCOUNTS.items():
            print(f"\n{'='*50}")
            _analyze_single_account(aid, name)
        return
    _analyze_single_account(account_id, account_name)


def _analyze_single_account(account_id, account_name):
    target_date = _latest_date()
    conn = _get_conn()

    # 账户级汇总
    row = conn.execute(
        """
        SELECT stat_cost, show_cnt, click_cnt, convert_cnt,
               message_action_cnt, clue_message_count,
               CASE WHEN show_cnt>0 THEN ROUND(click_cnt*100.0/show_cnt,2) END as ctr,
               CASE WHEN click_cnt>0 THEN ROUND(convert_cnt*100.0/click_cnt,2) END as cvr,
               CASE WHEN convert_cnt>0 THEN ROUND(stat_cost/convert_cnt,2) END as cpa
        FROM account_reports
        WHERE account_id = ? AND stat_date = ?
        """,
        (account_id, target_date),
    ).fetchone()

    print(f"\n  {account_name} | {target_date}")
    print(f"  {'─' * 40}")
    if not row or not row["stat_cost"]:
        print(f"  当日无消耗数据")
        conn.close()
        return

    print(f"  消耗:       ¥{_fmt_money(row['stat_cost'])}")
    print(f"  展示/点击:  {row['show_cnt']:,} / {row['click_cnt']:,}")
    print(f"  点击率:     {_fmt_pct(row['ctr'])}")
    print(f"  转化/留资:  {row['convert_cnt']} / {row['clue_message_count']}")
    print(f"  转化率:     {_fmt_pct(row['cvr'])}")
    print(f"  转化成本:   ¥{row['cpa'] or 0}")

    # 项目级明细
    projs = conn.execute(
        """
        SELECT project_name,
               SUM(stat_cost) as cost,
               SUM(convert_cnt) as converts,
               SUM(clue_message_count) as clues,
               CASE WHEN SUM(convert_cnt)>0 THEN ROUND(SUM(stat_cost)/SUM(convert_cnt),2) END as cpa
        FROM promotion_reports
        WHERE account_id = ? AND stat_date = ?
        GROUP BY project_id
        ORDER BY cost DESC
        LIMIT 8
        """,
        (account_id, target_date),
    ).fetchall()

    if projs:
        print(f"\n  项目明细:")
        data = []
        for p in projs:
            data.append([
                (p["project_name"] or "未知")[:22],
                f"¥{_fmt_money(p['cost'])}",
                f"{p['converts']}",
                f"{p['clues']}",
                f"¥{p['cpa'] or 0}",
            ])
        _print_table(data, ["项目", "消耗", "转化", "留资", "CPA"])

    conn.close()


def cmd_material(args):
    """素材分析"""
    account_id, account_name = _resolve_account(args.keyword)

    target_date = _latest_date("material_reports")
    conn = _get_conn()

    if account_id:
        rows = conn.execute(
            """
            SELECT material_id, material_name,
                   stat_cost, show_cnt, click_cnt, convert_cnt, clue_message_count,
                   CASE WHEN show_cnt>0 THEN ROUND(click_cnt*100.0/show_cnt,2) END as ctr,
                   CASE WHEN convert_cnt>0 THEN ROUND(stat_cost/convert_cnt,2) END as cpa
            FROM material_reports
            WHERE account_id = ? AND stat_date = ?
            ORDER BY stat_cost DESC
            LIMIT 20
            """,
            (account_id, target_date),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT m.material_id, MAX(m.material_name) as material_name,
                   MAX(a.name) as account_name,
                   SUM(m.stat_cost) as stat_cost,
                   SUM(m.show_cnt) as show_cnt,
                   SUM(m.click_cnt) as click_cnt,
                   SUM(m.convert_cnt) as convert_cnt,
                   SUM(m.clue_message_count) as clue_message_count,
                   CASE WHEN SUM(m.show_cnt)>0 THEN ROUND(SUM(m.click_cnt)*100.0/SUM(m.show_cnt),2) END as ctr,
                   CASE WHEN SUM(m.convert_cnt)>0 THEN ROUND(SUM(m.stat_cost)/SUM(m.convert_cnt),2) END as cpa
            FROM material_reports m
            LEFT JOIN accounts a ON m.account_id = a.account_id
            WHERE m.stat_date = ?
            GROUP BY m.material_id
            ORDER BY stat_cost DESC
            LIMIT 20
            """,
            (target_date,),
        ).fetchall()

    conn.close()

    if not rows:
        print(f"  {target_date} 无素材数据")
        return

    print(f"\n  素材排名 TOP20 | {account_name} | {target_date}")
    print(f"  {'─' * 70}")
    data = []
    for i, r in enumerate(rows, 1):
        mid = str(r["material_id"])[-8:]
        data.append([
            f"{i}",
            mid,
            f"¥{_fmt_money(r['stat_cost'])}",
            f"{r['convert_cnt']}",
            f"{r['clue_message_count']}",
            _fmt_pct(r["ctr"]),
            f"¥{r['cpa'] or 0}",
        ])
    _print_table(data, ["#", "素材ID尾号", "消耗", "转化", "留资", "CTR", "CPA"])
    print()


def cmd_material_decision(args):
    """素材四象限决策分析"""
    from src.analysis.material_decision import MaterialDecisionEngine
    engine = MaterialDecisionEngine()

    account_id, account_name = _resolve_account(args.keyword)
    if not account_id:
        print("  素材决策需要指定账户，例如: python ad.py 素材决策 成都")
        return

    detail = engine.get_account_detail(account_id)
    if not detail:
        print(f"  {account_name} 无决策数据")
        return

    print(f"\n  素材决策分析 | {account_name}")
    print(f"  {'─' * 50}")

    for quadrant in ["star", "potential", "watch", "eliminate"]:
        items = detail.get(quadrant, [])
        labels = {
            "star": "明星素材 (建议放量)",
            "potential": "潜力素材 (建议优化)",
            "watch": "观察素材 (继续测试)",
            "eliminate": "淘汰素材 (建议暂停)",
        }
        if not items:
            continue
        print(f"\n  [{labels[quadrant]}] ({len(items)}个)")
        for item in items[:5]:
            mid = str(item.get("material_id", ""))[-8:]
            cost = item.get("total_cost", 0)
            ctr = item.get("ctr", 0)
            cpa = item.get("cpa", 0)
            print(f"    {mid}  消耗¥{_fmt_money(cost)}  CTR {_fmt_pct(ctr)}  CPA ¥{cpa or 0}")
    print()


def cmd_projects(args):
    """项目级分析"""
    account_id, account_name = _resolve_account(args.keyword)
    if not account_id:
        print("  项目分析需要指定账户，例如: python ad.py 项目 成都")
        return

    target_date = _latest_date()
    conn = _get_conn()

    # 查最近7天的项目汇总
    start = (date.fromisoformat(target_date) - timedelta(days=7)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """
        SELECT project_id, MAX(project_name) as project_name,
               COUNT(DISTINCT promotion_id) as promotions,
               SUM(stat_cost) as cost,
               SUM(show_cnt) as shows,
               SUM(click_cnt) as clicks,
               SUM(convert_cnt) as converts,
               SUM(clue_message_count) as clues,
               CASE WHEN SUM(show_cnt)>0 THEN ROUND(SUM(click_cnt)*100.0/SUM(show_cnt),2) END as ctr,
               CASE WHEN SUM(convert_cnt)>0 THEN ROUND(SUM(stat_cost)/SUM(convert_cnt),2) END as cpa
        FROM promotion_reports
        WHERE account_id = ? AND stat_date BETWEEN ? AND ?
        GROUP BY project_id
        ORDER BY cost DESC
        """,
        (account_id, start, target_date),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"  {account_name} 最近7天无项目数据")
        return

    print(f"\n  项目分析 | {account_name} | {start} ~ {target_date}")
    print(f"  {'─' * 80}")
    data = []
    for i, r in enumerate(rows, 1):
        data.append([
            f"{i}",
            (r["project_name"] or "未知")[:22],
            f"{r['promotions']}",
            f"¥{_fmt_money(r['cost'])}",
            f"{r['converts']}",
            f"{r['clues']}",
            _fmt_pct(r["ctr"]),
            f"¥{r['cpa'] or 0}",
        ])
    _print_table(data, ["#", "项目名", "单元数", "消耗", "转化", "留资", "CTR", "CPA"])
    print()


def cmd_promotions(args):
    """投放单元级分析"""
    account_id, account_name = _resolve_account(args.keyword)
    if not account_id:
        print("  单元分析需要指定账户，例如: python ad.py 单元 成都")
        return

    target_date = _latest_date()
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT promotion_name, project_name,
               stat_cost, show_cnt, click_cnt, convert_cnt, clue_message_count,
               CASE WHEN show_cnt>0 THEN ROUND(click_cnt*100.0/show_cnt,2) END as ctr,
               CASE WHEN convert_cnt>0 THEN ROUND(stat_cost/convert_cnt,2) END as cpa
        FROM promotion_reports
        WHERE account_id = ? AND stat_date = ?
        ORDER BY stat_cost DESC
        LIMIT 15
        """,
        (account_id, target_date),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"  {account_name} {target_date} 无单元数据")
        return

    print(f"\n  投放单元 TOP15 | {account_name} | {target_date}")
    print(f"  {'─' * 80}")
    data = []
    for i, r in enumerate(rows, 1):
        data.append([
            f"{i}",
            (r["promotion_name"] or "未知")[:18],
            (r["project_name"] or "未知")[:14],
            f"¥{_fmt_money(r['stat_cost'])}",
            f"{r['converts']}" if "converts" in r.keys() else f"{r['convert_cnt']}",
            _fmt_pct(r["ctr"]),
            f"¥{r['cpa'] or 0}",
        ])
    _print_table(data, ["#", "单元名", "所属项目", "消耗", "转化", "CTR", "CPA"])
    print()


def cmd_accounts_list(args):
    """列出所有子账户"""
    from config.settings import LOCAL_SUB_ACCOUNTS
    conn = _get_conn()
    target_date = _latest_date()

    print(f"\n  子账户列表 | 共 {len(LOCAL_SUB_ACCOUNTS)} 个")
    print(f"  {'─' * 60}")
    for name, aid in LOCAL_SUB_ACCOUNTS.items():
        row = conn.execute(
            "SELECT stat_cost FROM account_reports WHERE account_id=? AND stat_date=?",
            (aid, target_date),
        ).fetchone()
        cost = f"¥{_fmt_money(row['stat_cost'])}" if row and row["stat_cost"] else "无消耗"
        print(f"  {name[:20]:<20s}  {aid}  {cost}")
    conn.close()
    print()


def cmd_reconcile(args):
    """对账检查: 账户总消耗 vs 单元消耗, 检测已删除实体缺口."""
    from config.settings import LOCAL_SUB_ACCOUNTS
    from src.api.client import OceanEngineClient
    from src.api.auth import AuthManager

    conn = _get_conn()
    latest = _latest_date()
    print(f"\n  对账检查 | 日期范围: 2026-06-01 ~ {latest}")
    print(f"  {'─' * 70}")

    total_gap = 0.0
    total_account_cost = 0.0
    accounts_with_gap = 0
    details = []

    for name, aid in LOCAL_SUB_ACCOUNTS.items():
        # DB 中的账户消耗
        acc_row = conn.execute(
            "SELECT SUM(stat_cost) as cost FROM account_reports "
            "WHERE account_id = ? AND stat_date BETWEEN '2026-06-01' AND ?",
            (aid, latest),
        ).fetchone()
        acc_cost = (acc_row["cost"] or 0) if acc_row else 0

        # DB 中的单元消耗
        promo_row = conn.execute(
            "SELECT SUM(stat_cost) as cost FROM promotion_reports "
            "WHERE account_id = ? AND stat_date BETWEEN '2026-06-01' AND ?",
            (aid, latest),
        ).fetchone()
        promo_cost = (promo_row["cost"] or 0) if promo_row else 0

        if acc_cost <= 0:
            continue

        total_account_cost += acc_cost
        gap = acc_cost - promo_cost

        if abs(gap) > 0.01:
            accounts_with_gap += 1
            total_gap += gap
            gap_pct = gap / acc_cost * 100
            details.append((name, aid, acc_cost, promo_cost, gap, gap_pct))

    conn.close()

    if accounts_with_gap:
        print(f"\n  ⚠️  发现 {accounts_with_gap} 个账户存在差异:")
        print(f"  {'─' * 80}")
        print(f"  {'账户':<22} | {'账户总消耗':>12} | {'单元总消耗':>12} | {'差异':>10} | %")
        print(f"  {'─' * 80}")
        for name, aid, acc, promo, gap, pct in sorted(details, key=lambda x: abs(x[5]), reverse=True):
            short = name[:20]
            print(f"  {short:<22} | ¥{acc:>11,.2f} | ¥{promo:>11,.2f} | ¥{gap:>9,.2f} | {pct:+.2f}%")
        print(f"  {'─' * 80}")
        print(f"  总差异: ¥{total_gap:,.2f} ({total_gap/total_account_cost*100:+.4f}%)")
        print(f"\n  💡 差异可能原因: 已删除的投放单元/项目有历史消耗但未在单元报表中体现。")
        print(f"  建议: 运行 'python ad.py 同步' 重新拉取最新数据。")
    else:
        print(f"  ✅ 所有 {len(LOCAL_SUB_ACCOUNTS)} 个账户完全对齐 (差异 < 0.01元)")
        print(f"  总消耗: ¥{total_account_cost:,.2f}")

    # 额外：检查是否有已删除实体
    print(f"\n  正在检查已删除的投放单元...")
    try:
        auth = AuthManager()
        client = OceanEngineClient(auth)
        total_deleted_promos = 0
        total_deleted_projects = 0

        for name, aid in LOCAL_SUB_ACCOUNTS.items():
            # 仅已删除的单元
            try:
                del_promos = client.get_promotion_list(
                    aid, status_filter="PROMOTION_STATUS_DELETED",
                )
                if del_promos:
                    total_deleted_promos += len(del_promos)
                    for dp in del_promos[:3]:
                        print(f"    [已删除单元] {dp.get('promotion_name','')[:25]}  ID={dp.get('promotion_id')}")
            except Exception:
                pass

            # 仅已删除的项目
            try:
                del_projs = client.get_project_list(
                    aid, status_filter="PROJECT_STATUS_DELETED",
                )
                if del_projs:
                    total_deleted_projects += len(del_projs)
                    for dp in del_projs[:3]:
                        print(f"    [已删除项目] {dp.get('project_name','')[:25]}  ID={dp.get('project_id')}")
            except Exception:
                pass

        print(f"\n  已删除单元: {total_deleted_promos} 个 | 已删除项目: {total_deleted_projects} 个")
        if total_deleted_promos == 0 and total_deleted_projects == 0:
            print(f"  ✅ 当前无已删除实体，数据完整")
    except Exception as e:
        print(f"  ⚠️  无法检查已删除实体: {e}")

    print()


def cmd_verify(args):
    """验证管道: 检查数据库归属覆盖率、API字段完整性、ETL逻辑."""
    import subprocess
    script = PROJECT_ROOT / "scripts" / "verify_pipeline.py"
    
    # 从 sys.argv 获取额外参数（日期）
    date_arg = sys.argv[2] if len(sys.argv) > 2 else None
    
    cmd = [sys.executable, str(script)]
    if date_arg:
        cmd.append(date_arg)
    subprocess.run(cmd)


# ── CLI ────────────────────────────────────────────────────

COMMAND_MAP = {
    "看板":      (cmd_dashboard,      "启动数据看板"),
    "同步":      (cmd_sync,           "同步数据 (可指定日期)"),
    "回填":      (cmd_backfill,       "回填历史数据"),
    "日报":      (cmd_report,         "生成投流日报"),
    "周报":      (cmd_report,         "生成投流周报"),
    "告警":      (cmd_alerts,         "检查异常告警"),
    "总览":      (cmd_overview,       "全局投流概览"),
    "排行":      (cmd_ranking,        "账户消耗排行"),
    "分析":      (cmd_analyze,        "分析指定账户"),
    "素材":      (cmd_material,       "素材排名 TOP20"),
    "素材决策":   (cmd_material_decision, "素材四象限决策"),
    "项目":      (cmd_projects,       "项目级分析"),
    "单元":      (cmd_promotions,     "投放单元级分析"),
    "账户列表":   (cmd_accounts_list,  "列出所有子账户"),
    "对账":      (cmd_reconcile,     "对账检查: 检测已删除实体缺口"),
    "验证":      (cmd_verify,        "验证管道: 归属覆盖率+字段完整性+ETL逻辑"),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        print("\n可用指令:")
        for cmd, (_, desc) in COMMAND_MAP.items():
            print(f"  python ad.py {cmd:<10s}  {desc}")
        return

    cmd_key = sys.argv[1]
    if cmd_key not in COMMAND_MAP:
        print(f"未知指令: {cmd_key}")
        print("运行 python ad.py help 查看可用指令")
        return

    func, _ = COMMAND_MAP[cmd_key]

    # 构建简单 args
    class Args:
        pass
    args = Args()
    args.port = 8888
    args.date = None
    args.days = 7
    args.keyword = None
    args.type = "日报"

    # 解析额外参数
    if len(sys.argv) > 2:
        extra = sys.argv[2]
        if cmd_key == "同步":
            args.date = extra
        elif cmd_key == "回填":
            args.days = int(extra)
        elif cmd_key == "周报":
            args.type = "周报"
        elif cmd_key in ("分析", "素材", "素材决策", "项目", "单元"):
            args.keyword = extra

    func(args)


if __name__ == "__main__":
    main()
