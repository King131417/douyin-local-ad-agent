#!/usr/bin/env python3
"""
Pipeline Verification Script
=============================
Run this after ANY code change to catch cross-layer breakages before they
reach the user. Checks:

1. SQLite upsert column count matches VALUES placeholders (prevents silent insert failures)
2. DB attribution coverage (% of materials with promotion_id / project_id)
3. All web API endpoints return attribution fields
4. Decision engine returns attribution fields in candidates

Usage:
    python scripts/verify_pipeline.py              # check latest date
    python scripts/verify_pipeline.py 2026-07-01   # check specific date
"""

import sys
import os
import sqlite3
import re
from pathlib import Path
from datetime import datetime

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH
from src.pipeline.storage import Storage
from src.analysis.material_decision import MaterialDecisionEngine

# ── Colors ──────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0
warnings = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  {GREEN}[PASS]{RESET} {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  {RED}[FAIL]{RESET} {msg}")


def warn(msg):
    global warnings
    warnings += 1
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def header(title):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN} {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")


# ── Test 1: SQLite Upsert Column Count ─────────────────────
def check_upsert_columns():
    header("1. SQLite Upsert Column Count Verification")
    print("  Checking if INSERT column count matches VALUES placeholder count...")

    storage = Storage()
    conn = sqlite3.connect(DATABASE_PATH)

    tables_to_check = [
        ("material_reports", "upsert_material_reports"),
        ("account_reports", "upsert_account_reports"),
        ("promotion_reports", "upsert_promotion_reports"),
        ("project_reports", "upsert_project_reports"),
    ]

    for table_name, method_name in tables_to_check:
        # Get the source code of the upsert method
        import inspect
        method = getattr(storage, method_name, None)
        if method is None:
            warn(f"{method_name} not found on Storage")
            continue

        source = inspect.getsource(method)

        # Extract the INSERT INTO ... VALUES (...) SQL
        # Look for the column list between INSERT INTO and VALUES
        insert_match = re.search(
            r"INSERT\s+INTO\s+" + table_name + r"\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
            source,
            re.DOTALL | re.IGNORECASE,
        )
        if not insert_match:
            warn(f"{table_name}: could not parse INSERT SQL from {method_name}")
            continue

        col_section = insert_match.group(1)
        val_section = insert_match.group(2)

        # Count actual column names (excluding dynamic {v15_cols} etc.)
        # Static columns are comma-separated identifiers
        static_cols = [c.strip() for c in col_section.split(",") if "{" not in c and "}" not in c]
        static_vals = [v.strip() for v in val_section.split(",") if "{" not in v and "}" not in v]

        # Check dynamic placeholders
        has_v15_cols = "{', '.join(v15_cols)}" in col_section or "{', '.join(" in col_section
        has_v15_placeholders = "{v15_placeholders}" in val_section

        if has_v15_cols and has_v15_placeholders:
            # Dynamic columns - check that v15_col_names and v15_placeholders use same length
            v15_cols = storage._v15_col_names()
            v15_placeholder_count = len(storage.V15_INSERT_COLS)  # this is what v15_placeholders generates
            if len(v15_cols) == v15_placeholder_count:
                ok(f"{table_name}: {len(static_cols)} static + {len(v15_cols)} v15 = {len(static_cols)+len(v15_cols)} cols, placeholders match")
            else:
                fail(f"{table_name}: v15 col_names({len(v15_cols)}) != placeholders({v15_placeholder_count})")
        elif len(static_cols) == len(static_vals):
            ok(f"{table_name}: {len(static_cols)} columns == {len(static_vals)} placeholders")
        else:
            fail(f"{table_name}: {len(static_cols)} columns != {len(static_vals)} placeholders (MISMATCH!)")
            print(f"       Columns: {static_cols}")
            print(f"       Values:  {static_vals}")

    conn.close()


# ── Test 2: DB Attribution Coverage ────────────────────────
def check_attribution_coverage(date_str=None):
    header("2. Database Attribution Coverage")

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    if date_str is None:
        row = conn.execute(
            "SELECT MAX(stat_date) as d FROM material_reports"
        ).fetchone()
        date_str = row["d"] if row and row["d"] else None
        if not date_str:
            warn("No material_reports data found in DB")
            conn.close()
            return
        print(f"  Using latest date: {date_str}")

    row = conn.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN promotion_id IS NOT NULL AND promotion_id != '' THEN 1 ELSE 0 END) as has_promo,
            SUM(CASE WHEN project_id IS NOT NULL AND project_id != '' THEN 1 ELSE 0 END) as has_proj,
            SUM(CASE WHEN promotion_name IS NOT NULL AND promotion_name != '' THEN 1 ELSE 0 END) as has_promo_name,
            SUM(CASE WHEN project_name IS NOT NULL AND project_name != '' THEN 1 ELSE 0 END) as has_proj_name
        FROM material_reports WHERE stat_date = ?
        """,
        (date_str,),
    ).fetchone()

    total = row["total"]
    if total == 0:
        warn(f"No materials found for {date_str}")
        conn.close()
        return

    promo_pct = (row["has_promo"] / total) * 100
    proj_pct = (row["has_proj"] / total) * 100

    print(f"  Date: {date_str}")
    print(f"  Total materials: {total}")
    print(f"  Has promotion_id: {row['has_promo']}/{total} ({promo_pct:.1f}%)")
    print(f"  Has project_id:   {row['has_proj']}/{total} ({proj_pct:.1f}%)")
    print(f"  Has promotion_name: {row['has_promo_name']}/{total}")
    print(f"  Has project_name:   {row['has_proj_name']}/{total}")

    if promo_pct == 100 and proj_pct == 100:
        ok(f"100% attribution coverage")
    elif promo_pct >= 90 and proj_pct >= 90:
        warn(f"Attribution coverage {promo_pct:.0f}%/{proj_pct:.0f}% (target: 100%)")
    else:
        fail(f"Low attribution coverage: promo={promo_pct:.0f}%, proj={proj_pct:.0f}%")

    # Also check per-account breakdown
    print(f"\n  Per-account breakdown:")
    acct_rows = conn.execute(
        """
        SELECT account_id,
               COUNT(*) as total,
               SUM(CASE WHEN promotion_id IS NOT NULL AND promotion_id != '' THEN 1 ELSE 0 END) as has_promo
        FROM material_reports WHERE stat_date = ?
        GROUP BY account_id ORDER BY total DESC
        """,
        (date_str,),
    ).fetchall()

    for ar in acct_rows:
        pct = (ar["has_promo"] / ar["total"]) * 100 if ar["total"] > 0 else 0
        status = f"{GREEN}OK{RESET}" if pct == 100 else f"{RED}MISS{RESET}"
        if pct < 100:
            print(f"    {status} {ar['account_id'][-8:]}: {ar['has_promo']}/{ar['total']} ({pct:.0f}%)")
        else:
            print(f"    {status} {ar['account_id'][-8:]}: {ar['has_promo']}/{ar['total']} ({pct:.0f}%)")

    conn.close()
    return date_str


# ── Test 3: Decision Engine Attribution ────────────────────
def check_decision_engine(date_str):
    header("3. Decision Engine Attribution Fields")

    storage = Storage()
    engine = MaterialDecisionEngine(storage)

    try:
        result = engine.analyze(date_str=date_str)
    except Exception as e:
        fail(f"Decision engine crashed: {e}")
        return

    for list_name in ["scale_up_candidates", "pause_candidates"]:
        items = result.get(list_name, [])
        if not items:
            warn(f"{list_name}: empty list")
            continue

        has_promo = sum(1 for m in items if m.get("promotion_name"))
        has_proj = sum(1 for m in items if m.get("project_name"))
        pct_promo = (has_promo / len(items)) * 100
        pct_proj = (has_proj / len(items)) * 100

        if pct_promo == 100 and pct_proj == 100:
            ok(f"{list_name}: {len(items)} items, 100% have promotion_name + project_name")
        elif pct_promo >= 90 and pct_proj >= 90:
            warn(f"{list_name}: {len(items)} items, promo={pct_promo:.0f}%, proj={pct_proj:.0f}%")
        else:
            fail(f"{list_name}: {len(items)} items, promo={pct_promo:.0f}%, proj={pct_proj:.0f}%")

    # Also check account detail
    accounts = storage.get_accounts(active_only=False)
    if accounts:
        aid = accounts[0]["account_id"]
        try:
            detail = engine.get_account_detail(aid, date_str)
            mats = detail.get("materials", [])
            if mats:
                has_promo = sum(1 for m in mats if m.get("promotion_name"))
                pct = (has_promo / len(mats)) * 100
                if pct == 100:
                    ok(f"get_account_detail({aid[-8:]}): {len(mats)} materials, 100% have promotion_name")
                else:
                    fail(f"get_account_detail({aid[-8:]}): {len(mats)} materials, only {pct:.0f}% have promotion_name")
            else:
                warn(f"get_account_detail({aid[-8:]}): no materials")
        except Exception as e:
            fail(f"get_account_detail crashed: {e}")


# ── Test 4: Web API Endpoints ──────────────────────────────
def check_web_apis(date_str):
    header("4. Web API Endpoint Attribution Fields")

    import requests
    base = "http://127.0.0.1:8888"

    # Check if server is running
    try:
        requests.get(f"{base}/", timeout=2)
    except Exception:
        warn("Dashboard server not running on :8888, skipping API checks")
        warn("Start it with: python ad.py 看板")
        return

    endpoints = [
        (f"/api/decision?date={date_str}", "scale_up_candidates", "promotion_name"),
        (f"/api/ranking?date={date_str}", "materials", "promotion_name"),
    ]

    for path, list_key, field in endpoints:
        try:
            resp = requests.get(f"{base}{path}", timeout=10)
            if resp.status_code != 200:
                fail(f"{path}: HTTP {resp.status_code}")
                continue
            data = resp.json()
            items = data.get(list_key, [])
            if not items:
                warn(f"{path}: {list_key} is empty")
                continue
            has_field = sum(1 for m in items if m.get(field))
            pct = (has_field / len(items)) * 100
            if pct == 100:
                ok(f"{path}: {len(items)} items, 100% have {field}")
            else:
                fail(f"{path}: {len(items)} items, only {pct:.0f}% have {field}")
        except Exception as e:
            fail(f"{path}: {e}")

    # Check account detail API
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT DISTINCT account_id FROM material_reports WHERE stat_date = ? LIMIT 1",
        (date_str,),
    ).fetchone()
    conn.close()

    if row:
        aid = row["account_id"]
        try:
            resp = requests.get(f"{base}/api/account/{aid}?date={date_str}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                mats = data.get("materials", [])
                if mats:
                    has_promo = sum(1 for m in mats if m.get("promotion_name"))
                    pct = (has_promo / len(mats)) * 100
                    if pct == 100:
                        ok(f"/api/account/{aid[-8:]}: {len(mats)} materials, 100% have promotion_name")
                    else:
                        fail(f"/api/account/{aid[-8:]}: {len(mats)} materials, only {pct:.0f}% have promotion_name")
                else:
                    warn(f"/api/account/{aid[-8:]}: no materials")
            else:
                fail(f"/api/account/{aid[-8:]}: HTTP {resp.status_code}")
        except Exception as e:
            fail(f"/api/account/{aid[-8:]}: {e}")


# ── Test 5: ETL Attribution Logic ──────────────────────────
def check_etl_logic():
    header("5. ETL Attribution Logic Check")
    print("  Verifying _sync_account_materials has attribution injection...")

    import inspect
    from src.pipeline.etl import ETLPipeline

    etl = ETLPipeline.__new__(ETLPipeline)  # Don't init (avoids API calls)
    source = inspect.getsource(etl._sync_account_materials)

    checks = [
        ("promotion_id injection", 'r["promotion_id"]'),
        ("promotion_name injection", 'r["promotion_name"]'),
        ("project_id injection", 'r["project_id"]'),
        ("project_name injection", 'r["project_name"]'),
        ("DB fallback for promotions", "promotion_reports"),
        ("Single-promotion bulk fallback", "len(promotions) == 1"),
        ("Bulk fallback exists", "get_material_report(account_id, start_date, end_date)"),
    ]

    for label, pattern in checks:
        if pattern in source:
            ok(f"{label}: found")
        else:
            fail(f"{label}: MISSING from _sync_account_materials")


# ── Main ───────────────────────────────────────────────────
def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"{BOLD}{CYAN}")
    print("=" * 60)
    print("  Pipeline Verification Script")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(RESET)

    check_upsert_columns()
    date_str = check_attribution_coverage(date_arg)
    if date_str:
        check_decision_engine(date_str)
        check_web_apis(date_str)
    check_etl_logic()

    # Summary
    header("Summary")
    total = passed + failed + warnings
    print(f"  {GREEN}Passed: {passed}/{total}{RESET}")
    if warnings:
        print(f"  {YELLOW}Warnings: {warnings}/{total}{RESET}")
    if failed:
        print(f"  {RED}Failed: {failed}/{total}{RESET}")
        print(f"\n  {RED}{BOLD}ACTION REQUIRED: Fix failing checks before deploying!{RESET}")
        sys.exit(1)
    else:
        print(f"\n  {GREEN}{BOLD}All critical checks passed!{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
