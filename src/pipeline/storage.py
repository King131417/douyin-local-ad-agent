"""
SQLite Storage Layer — Account-Centric Schema

Tables:
- accounts:        Account metadata (id, name, status)
- account_reports: Daily aggregated metrics per account
- promotion_reports: Optional promotion-level detail
- optimization_log: Optimization suggestions and history
"""

import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime

from config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    name TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    first_seen TEXT DEFAULT (datetime('now')),
    last_seen TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS account_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    stat_date TEXT NOT NULL,
    -- Core metrics
    stat_cost REAL DEFAULT 0,
    show_cnt INTEGER DEFAULT 0,
    click_cnt INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0,
    convert_cnt INTEGER DEFAULT 0,
    -- Local ad specific metrics
    message_action_cnt INTEGER DEFAULT 0,
    clue_message_count INTEGER DEFAULT 0,
    phone_confirm_cnt INTEGER DEFAULT 0,
    phone_connect_cnt INTEGER DEFAULT 0,
    clue_pay_order_cnt INTEGER DEFAULT 0,
    -- Calculated fields
    cpm REAL DEFAULT 0,
    cpc REAL DEFAULT 0,
    cpa REAL DEFAULT 0,
    cvr REAL DEFAULT 0,
    -- Delivery type: 'total' (合并), 'general' (通投), 'searching' (搜索)
    delivery_type TEXT NOT NULL DEFAULT 'total',
    -- Full raw response
    raw_data TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(account_id, stat_date, delivery_type)
);

CREATE TABLE IF NOT EXISTS promotion_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    promotion_id TEXT,
    promotion_name TEXT,
    promotion_status TEXT,
    project_id TEXT,
    project_name TEXT,
    local_life_shop_id TEXT,
    local_life_shop_name TEXT,
    stat_date TEXT NOT NULL,
    -- Promotion metrics
    stat_cost REAL DEFAULT 0,
    show_cnt INTEGER DEFAULT 0,
    click_cnt INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0,
    cpc_platform REAL DEFAULT 0,
    cpm_platform REAL DEFAULT 0,
    convert_cnt INTEGER DEFAULT 0,
    conversion_cost REAL DEFAULT 0,
    conversion_rate REAL DEFAULT 0,
    message_action_cnt INTEGER DEFAULT 0,
    clue_message_count INTEGER DEFAULT 0,
    raw_data TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(account_id, promotion_id, stat_date)
);

CREATE TABLE IF NOT EXISTS material_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    material_name TEXT DEFAULT '',
    material_type TEXT DEFAULT '',
    stat_date TEXT NOT NULL,
    stat_cost REAL DEFAULT 0,
    show_cnt INTEGER DEFAULT 0,
    click_cnt INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0,
    cpc_platform REAL DEFAULT 0,
    cpm_platform REAL DEFAULT 0,
    convert_cnt INTEGER DEFAULT 0,
    conversion_cost REAL DEFAULT 0,
    conversion_rate REAL DEFAULT 0,
    form_cnt INTEGER DEFAULT 0,
    message_action_cnt INTEGER DEFAULT 0,
    clue_message_count INTEGER DEFAULT 0,
    raw_data TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(account_id, material_id, stat_date)
);

CREATE TABLE IF NOT EXISTS project_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    project_id TEXT,
    project_name TEXT,
    stat_date TEXT NOT NULL,
    stat_cost REAL DEFAULT 0,
    show_cnt INTEGER DEFAULT 0,
    click_cnt INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0,
    cpc_platform REAL DEFAULT 0,
    cpm_platform REAL DEFAULT 0,
    convert_cnt INTEGER DEFAULT 0,
    conversion_cost REAL DEFAULT 0,
    conversion_rate REAL DEFAULT 0,
    message_action_cnt INTEGER DEFAULT 0,
    clue_message_count INTEGER DEFAULT 0,
    raw_data TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(account_id, project_id, stat_date)
);

CREATE TABLE IF NOT EXISTS optimization_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    promotion_id TEXT,
    rule_name TEXT,
    condition_met TEXT,
    suggestion TEXT,
    action_taken TEXT,
    metrics_snapshot TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ar_account_date ON account_reports(account_id, stat_date);
CREATE INDEX IF NOT EXISTS idx_ar_date ON account_reports(stat_date);
CREATE INDEX IF NOT EXISTS idx_pr_account_date ON promotion_reports(account_id, stat_date);
CREATE INDEX IF NOT EXISTS idx_mr_account_date ON material_reports(account_id, stat_date);
CREATE INDEX IF NOT EXISTS idx_mr_material ON material_reports(material_id);
CREATE INDEX IF NOT EXISTS idx_opt_log_date ON optimization_log(created_at);
"""


class Storage:
    """SQLite data store for local ad metrics."""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        
        # Migration: add delivery_type column if missing (pre-v3.0 DBs)
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(account_reports)").fetchall()]
            if "delivery_type" not in cols:
                logger.info("Migration: adding delivery_type column to account_reports...")
                # Check if old data exists
                old_count = conn.execute("SELECT COUNT(*) as cnt FROM account_reports").fetchone()["cnt"]
                # Rebuild table with new UNIQUE constraint and delivery_type at the end
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS _ar_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id TEXT NOT NULL,
                        stat_date TEXT NOT NULL,
                        stat_cost REAL DEFAULT 0, show_cnt INTEGER DEFAULT 0,
                        click_cnt INTEGER DEFAULT 0, ctr REAL DEFAULT 0,
                        convert_cnt INTEGER DEFAULT 0,
                        message_action_cnt INTEGER DEFAULT 0,
                        clue_message_count INTEGER DEFAULT 0,
                        phone_confirm_cnt INTEGER DEFAULT 0,
                        phone_connect_cnt INTEGER DEFAULT 0,
                        clue_pay_order_cnt INTEGER DEFAULT 0,
                        cpm REAL DEFAULT 0, cpc REAL DEFAULT 0,
                        cpa REAL DEFAULT 0, cvr REAL DEFAULT 0,
                        delivery_type TEXT NOT NULL DEFAULT 'total',
                        raw_data TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now')),
                        UNIQUE(account_id, stat_date, delivery_type)
                    );
                    INSERT INTO _ar_new (id, account_id, stat_date, stat_cost, show_cnt,
                        click_cnt, ctr, convert_cnt, message_action_cnt, clue_message_count,
                        phone_confirm_cnt, phone_connect_cnt, clue_pay_order_cnt,
                        cpm, cpc, cpa, cvr, raw_data, created_at, updated_at)
                    SELECT id, account_id, stat_date, stat_cost, show_cnt,
                        click_cnt, ctr, convert_cnt, message_action_cnt, clue_message_count,
                        phone_confirm_cnt, phone_connect_cnt, clue_pay_order_cnt,
                        cpm, cpc, cpa, cvr, raw_data, created_at, updated_at
                    FROM account_reports;
                    DROP TABLE account_reports;
                    ALTER TABLE _ar_new RENAME TO account_reports;
                """)
                # Recreate indexes
                conn.executescript("""
                    CREATE INDEX IF NOT EXISTS idx_ar_account_date ON account_reports(account_id, stat_date);
                    CREATE INDEX IF NOT EXISTS idx_ar_date ON account_reports(stat_date);
                """)
                new_count = conn.execute("SELECT COUNT(*) as cnt FROM account_reports").fetchone()["cnt"]
                logger.info("Migration: delivery_type added. %d rows migrated (was %d)", new_count, old_count)
        except Exception as e:
            logger.warning("Migration check failed (non-critical): %s", e)
        
        # Migration v1.4: add API-native metric columns to existing tables
        self._migrate_v14(conn)

        # Migration v1.5: add attribution(计费时间) metric columns
        self._migrate_v15(conn)

        conn.commit()
        conn.close()
        logger.info("Database initialized: %s", self.db_path)

    def _migrate_v14(self, conn: sqlite3.Connection):
        """Add API-native calculated metric columns (v1.4)."""
        additions = {
            "account_reports": [
                ("cpc_platform", "REAL DEFAULT 0"),
                ("cpm_platform", "REAL DEFAULT 0"),
                ("conversion_cost", "REAL DEFAULT 0"),
                ("conversion_rate", "REAL DEFAULT 0"),
                ("form_cnt", "INTEGER DEFAULT 0"),
            ],
            "promotion_reports": [
                ("cpc_platform", "REAL DEFAULT 0"),
                ("cpm_platform", "REAL DEFAULT 0"),
                ("conversion_cost", "REAL DEFAULT 0"),
                ("conversion_rate", "REAL DEFAULT 0"),
            ],
            "material_reports": [
                ("cpc_platform", "REAL DEFAULT 0"),
                ("cpm_platform", "REAL DEFAULT 0"),
                ("conversion_cost", "REAL DEFAULT 0"),
                ("conversion_rate", "REAL DEFAULT 0"),
                ("form_cnt", "INTEGER DEFAULT 0"),
            ],
        }
        for table, cols in additions.items():
            existing = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            for col_name, col_type in cols:
                if col_name not in existing:
                    try:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                        logger.info("Migration v1.4: added %s.%s %s", table, col_name, col_type)
                    except Exception as e:
                        logger.warning("Migration %s.%s failed: %s", table, col_name, e)

    def _migrate_v15(self, conn: sqlite3.Connection):
        """Add v1.5 expanded metrics: attribution/intention/live/video columns.
        
        Full raw API response always stored in raw_data JSON.
        These columns are the most useful subset for dashboard queries.
        """
        additions = {
            "account_reports": [
                # 计费时间（与后台UI对齐的核心指标）
                ("attribution_message_action_cnt", "INTEGER DEFAULT 0"),
                ("attribution_convert_cnt", "INTEGER DEFAULT 0"),
                ("attribution_conversion_rate", "REAL DEFAULT 0"),
                ("attribution_form_cnt", "INTEGER DEFAULT 0"),
                ("attribution_clue_pay_order_cnt", "INTEGER DEFAULT 0"),
                # 意向指标
                ("intention_message_clue_cnt", "INTEGER DEFAULT 0"),
                ("intention_form_cnt", "INTEGER DEFAULT 0"),
                ("intention_phone_cnt", "INTEGER DEFAULT 0"),
                # 直播指标
                ("luban_live_enter_cnt", "INTEGER DEFAULT 0"),
                ("live_watch_one_minute_count", "INTEGER DEFAULT 0"),
                # 视频播放
                ("play_duration_5s", "INTEGER DEFAULT 0"),
            ],
            "promotion_reports": [
                ("attribution_message_action_cnt", "INTEGER DEFAULT 0"),
                ("attribution_convert_cnt", "INTEGER DEFAULT 0"),
                ("attribution_conversion_rate", "REAL DEFAULT 0"),
                ("attribution_form_cnt", "INTEGER DEFAULT 0"),
                ("attribution_clue_pay_order_cnt", "INTEGER DEFAULT 0"),
                ("intention_message_clue_cnt", "INTEGER DEFAULT 0"),
                ("luban_live_enter_cnt", "INTEGER DEFAULT 0"),
                ("play_duration_5s", "INTEGER DEFAULT 0"),
            ],
            "material_reports": [
                ("attribution_message_action_cnt", "INTEGER DEFAULT 0"),
                ("attribution_convert_cnt", "INTEGER DEFAULT 0"),
                ("attribution_conversion_rate", "REAL DEFAULT 0"),
                ("attribution_form_cnt", "INTEGER DEFAULT 0"),
                ("attribution_clue_pay_order_cnt", "INTEGER DEFAULT 0"),
                ("intention_message_clue_cnt", "INTEGER DEFAULT 0"),
                ("luban_live_enter_cnt", "INTEGER DEFAULT 0"),
                ("play_duration_5s", "INTEGER DEFAULT 0"),
            ],
            "project_reports": [
                ("attribution_message_action_cnt", "INTEGER DEFAULT 0"),
                ("attribution_convert_cnt", "INTEGER DEFAULT 0"),
                ("attribution_conversion_rate", "REAL DEFAULT 0"),
                ("attribution_form_cnt", "INTEGER DEFAULT 0"),
                ("attribution_clue_pay_order_cnt", "INTEGER DEFAULT 0"),
                ("intention_message_clue_cnt", "INTEGER DEFAULT 0"),
                ("luban_live_enter_cnt", "INTEGER DEFAULT 0"),
                ("play_duration_5s", "INTEGER DEFAULT 0"),
            ],
        }

        # v1.6: Add promotion/project attribution to material_reports
        _migrate_v16_cols = {
            "material_reports": [
                ("promotion_id", "TEXT DEFAULT ''"),
                ("promotion_name", "TEXT DEFAULT ''"),
                ("project_id", "TEXT DEFAULT ''"),
                ("project_name", "TEXT DEFAULT ''"),
            ],
        }
        for table, cols in _migrate_v16_cols.items():
            existing = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            for col_name, col_type in cols:
                if col_name not in existing:
                    try:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                        logger.info("Migration v1.6: added %s.%s %s", table, col_name, col_type)
                    except Exception as e:
                        logger.warning("Migration v1.6 %s.%s failed: %s", table, col_name, e)
        for table, cols in additions.items():
            existing = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            for col_name, col_type in cols:
                if col_name not in existing:
                    try:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                        logger.info("Migration v1.5: added %s.%s %s", table, col_name, col_type)
                    except Exception as e:
                        logger.warning("Migration v1.5 %s.%s failed: %s", table, col_name, e)

    # v1.5 expanded fields columns (same across all report tables)
    # These map API response keys → DB column names (identical).
    V15_INSERT_COLS = [
        "attribution_message_action_cnt", "attribution_convert_cnt",
        "attribution_conversion_rate", "attribution_form_cnt",
        "attribution_clue_pay_order_cnt",
        "intention_message_clue_cnt",
        "luban_live_enter_cnt", "play_duration_5s",
    ]
    # account_reports has 3 extra v1.5 columns
    V15_ACCOUNT_EXTRA = ["intention_form_cnt", "intention_phone_cnt", "live_watch_one_minute_count"]

    def _v15_row_values(self, row: dict, extra: list[str] | None = None) -> list:
        """Extract v1.5 column values from API row."""
        all_cols = self.V15_INSERT_COLS + (extra or [])
        return [self._int(row, c) if "cnt" in c else self._float(row, c) for c in all_cols]

    def _v15_col_names(self, extra: list[str] | None = None) -> list[str]:
        return self.V15_INSERT_COLS + (extra or [])

    def _v15_update_clause(self, extra: list[str] | None = None) -> str:
        """Generate DO UPDATE SET clause for v1.5 columns."""
        all_cols = self.V15_INSERT_COLS + (extra or [])
        return ", ".join(f"{c}=excluded.{c}" for c in all_cols)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Account Management ─────────────────────────────────────

    def ensure_account(self, account_id: str, name: str = ""):
        """Register or update an account."""
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO accounts (account_id, name, last_seen)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(account_id) DO UPDATE SET
                name = CASE WHEN excluded.name != '' THEN excluded.name ELSE name END,
                last_seen = datetime('now')
            """,
            (str(account_id), name),
        )
        conn.commit()

    def get_accounts(self, active_only: bool = True) -> list[dict]:
        """Get all accounts, optionally only active ones."""
        conn = self._get_conn()
        query = "SELECT * FROM accounts"
        if active_only:
            query += " WHERE status = 'active'"
        query += " ORDER BY account_id"
        return [dict(r) for r in conn.execute(query).fetchall()]

    def get_account_ids(self) -> list[str]:
        """Get list of active account IDs."""
        return [r["account_id"] for r in self.get_accounts()]

    def get_account_name_map(self) -> dict[str, str]:
        """Get {account_id: name} mapping for all accounts."""
        return {r["account_id"]: r["name"] for r in self.get_accounts()}

    # ── Account Reports ────────────────────────────────────────

    def upsert_account_reports(
        self, account_id: str, rows: list[dict],
        delivery_type: str = "total",
    ) -> int:
        """Insert/update daily account-level report rows.
        
        Args:
            account_id: The local account ID
            rows: List of daily report rows from API
            delivery_type: 'total', 'general' (通投), or 'searching' (搜索)
        """
        conn = self._get_conn()
        count = 0
        v15_extra = self.V15_ACCOUNT_EXTRA
        v15_cols = self._v15_col_names(v15_extra)
        v15_placeholders = ", ".join(["?"] * len(v15_cols))
        v15_update = self._v15_update_clause(v15_extra)
        for row in rows:
            try:
                v15_vals = self._v15_row_values(row, v15_extra)
                conn.execute(
                    f"""
                    INSERT INTO account_reports (
                        account_id, stat_date, delivery_type,
                        stat_cost, show_cnt, click_cnt, ctr, convert_cnt,
                        cpc_platform, cpm_platform, conversion_cost, conversion_rate, form_cnt,
                        message_action_cnt, clue_message_count,
                        phone_confirm_cnt, phone_connect_cnt, clue_pay_order_cnt,
                        {', '.join(v15_cols)},
                        cpm, cpc, cpa, cvr, raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {v15_placeholders}, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, stat_date, delivery_type)
                    DO UPDATE SET
                        stat_cost=excluded.stat_cost, show_cnt=excluded.show_cnt,
                        click_cnt=excluded.click_cnt, ctr=excluded.ctr,
                        convert_cnt=excluded.convert_cnt,
                        cpc_platform=excluded.cpc_platform,
                        cpm_platform=excluded.cpm_platform,
                        conversion_cost=excluded.conversion_cost,
                        conversion_rate=excluded.conversion_rate,
                        form_cnt=excluded.form_cnt,
                        message_action_cnt=excluded.message_action_cnt,
                        clue_message_count=excluded.clue_message_count,
                        phone_confirm_cnt=excluded.phone_confirm_cnt,
                        phone_connect_cnt=excluded.phone_connect_cnt,
                        clue_pay_order_cnt=excluded.clue_pay_order_cnt,
                        {v15_update},
                        cpm=excluded.cpm, cpc=excluded.cpc,
                        cpa=excluded.cpa, cvr=excluded.cvr,
                        raw_data=excluded.raw_data, updated_at=datetime('now')
                    """,
                    (
                        account_id,
                        row.get("stat_time_day", row.get("stat_date", "")),
                        delivery_type,
                        self._float(row, "stat_cost"),
                        self._int(row, "show_cnt"),
                        self._int(row, "click_cnt"),
                        self._float(row, "ctr"),
                        self._int(row, "convert_cnt"),
                        self._float(row, "cpc_platform"),
                        self._float(row, "cpm_platform"),
                        self._float(row, "conversion_cost"),
                        self._float(row, "conversion_rate"),
                        self._int(row, "form_cnt"),
                        self._int(row, "message_action_cnt"),
                        self._int(row, "clue_message_count"),
                        self._int(row, "phone_confirm_cnt"),
                        self._int(row, "phone_connect_cnt"),
                        self._int(row, "clue_pay_order_cnt"),
                        *v15_vals,
                        self._calc_cpm(row),
                        self._calc_cpc(row),
                        self._calc_cpa(row),
                        self._calc_cvr(row),
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )
                count += 1
            except Exception as e:
                logger.warning("Upsert failed for %s (%s): %s", account_id, delivery_type, e)

        conn.commit()
        return count

    def _float(self, row: dict, key: str) -> float:
        val = row.get(key, 0)
        if val is None or val == "":
            return 0.0
        return float(val)

    def _int(self, row: dict, key: str) -> int:
        val = row.get(key, 0)
        if val is None or val == "":
            return 0
        return int(float(val))

    def _calc_cpm(self, row: dict) -> float:
        cost = self._float(row, "stat_cost")
        show = self._int(row, "show_cnt")
        return round(cost / show * 1000, 2) if show > 0 else 0.0

    def _calc_cpc(self, row: dict) -> float:
        cost = self._float(row, "stat_cost")
        click = self._int(row, "click_cnt")
        return round(cost / click, 2) if click > 0 else 0.0

    def _calc_cpa(self, row: dict) -> float:
        cost = self._float(row, "stat_cost")
        convert = self._int(row, "convert_cnt")
        return round(cost / convert, 2) if convert > 0 else 0.0

    def _calc_cvr(self, row: dict) -> float:
        click = self._int(row, "click_cnt")
        convert = self._int(row, "convert_cnt")
        return round(convert / click * 100, 2) if click > 0 else 0.0

    # ── Queries ────────────────────────────────────────────────

    def get_account_reports(
        self,
        account_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1000,
        delivery_type: str = "total",
    ) -> list[dict]:
        """Query account-level reports with optional filters."""
        conn = self._get_conn()
        conditions = ["delivery_type = ?"]
        params: list = [delivery_type]
        if account_id:
            conditions.append("account_id = ?")
            params.append(account_id)
        if start_date:
            conditions.append("stat_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("stat_date <= ?")
            params.append(end_date)

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM account_reports WHERE {where} ORDER BY stat_date DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_daily_summary(self, date_str: str, account_id: str | None = None,
                          delivery_type: str = "total") -> dict:
        """Get daily aggregated summary across all accounts or a single account."""
        conn = self._get_conn()
        conditions = ["stat_date = ?", "delivery_type = ?"]
        params = [date_str, delivery_type]
        if account_id:
            conditions.append("account_id = ?")
            params.append(account_id)

        where = " AND ".join(conditions)
        row = conn.execute(
            f"""
            SELECT
                SUM(stat_cost) as total_cost,
                SUM(show_cnt) as total_show,
                SUM(click_cnt) as total_click,
                SUM(convert_cnt) as total_convert,
                SUM(message_action_cnt) as total_consult,
                SUM(clue_message_count) as total_clue,
                COUNT(DISTINCT account_id) as account_count,
                CASE WHEN SUM(show_cnt) > 0
                    THEN ROUND(SUM(click_cnt)*100.0/SUM(show_cnt), 2) END as ctr,
                CASE WHEN SUM(click_cnt) > 0
                    THEN ROUND(SUM(convert_cnt)*100.0/SUM(click_cnt), 2) END as cvr,
                CASE WHEN SUM(convert_cnt) > 0
                    THEN ROUND(SUM(stat_cost)/SUM(convert_cnt), 2) END as cpa
            FROM account_reports
            WHERE {where}
            """,
            params,
        ).fetchone()
        return dict(row) if row else {}

    def get_trend(
        self,
        start_date: str,
        end_date: str,
        account_id: str | None = None,
        delivery_type: str = "total",
    ) -> list[dict]:
        """Get daily trend data for a date range."""
        conn = self._get_conn()
        conditions = ["stat_date BETWEEN ? AND ?", "delivery_type = ?"]
        params = [start_date, end_date, delivery_type]
        if account_id:
            conditions.append("account_id = ?")
            params.append(account_id)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"""
            SELECT
                stat_date,
                SUM(stat_cost) as total_cost,
                SUM(show_cnt) as total_show,
                SUM(click_cnt) as total_click,
                SUM(convert_cnt) as total_convert,
                SUM(message_action_cnt) as total_consult,
                SUM(clue_message_count) as total_clue,
                COUNT(DISTINCT account_id) as account_count,
                CASE WHEN SUM(show_cnt) > 0
                    THEN ROUND(SUM(click_cnt)*100.0/SUM(show_cnt), 2) END as ctr,
                CASE WHEN SUM(click_cnt) > 0
                    THEN ROUND(SUM(convert_cnt)*100.0/SUM(click_cnt), 2) END as cvr,
                CASE WHEN SUM(convert_cnt) > 0
                    THEN ROUND(SUM(stat_cost)/SUM(convert_cnt), 2) END as cpa
            FROM account_reports
            WHERE {where}
            GROUP BY stat_date
            ORDER BY stat_date
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_account_ranking(
        self,
        start_date: str,
        end_date: str,
        top_n: int = 10,
        delivery_type: str = "total",
    ) -> list[dict]:
        """Rank accounts by total cost in a date range."""
        conn = self._get_conn()
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
                CASE WHEN SUM(r.convert_cnt) > 0
                    THEN ROUND(SUM(r.stat_cost)/SUM(r.convert_cnt), 2) END as cpa
            FROM account_reports r
            LEFT JOIN accounts a ON r.account_id = a.account_id
            WHERE r.stat_date BETWEEN ? AND ?
              AND r.delivery_type = ?
            GROUP BY r.account_id
            ORDER BY SUM(r.stat_cost) DESC
            LIMIT ?
            """,
            (start_date, end_date, delivery_type, top_n),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Material Reports ───────────────────────────────────────

    def upsert_material_reports(self, account_id: str, rows: list[dict]) -> int:
        """Insert/update material-level report rows.

        Each row dict may contain optional attribution fields:
          promotion_id, promotion_name, project_id, project_name
        These are populated when syncing via per-promotion material queries.
        """
        conn = self._get_conn()
        count = 0
        v15_cols = self._v15_col_names()
        v15_placeholders = ", ".join(["?"] * len(v15_cols))
        v15_update = self._v15_update_clause()
        for row in rows:
            try:
                v15_vals = self._v15_row_values(row)
                conn.execute(
                    f"""
                    INSERT INTO material_reports (
                        account_id, material_id, material_name, material_type, stat_date,
                        stat_cost, show_cnt, click_cnt, ctr,
                        cpc_platform, cpm_platform,
                        convert_cnt, conversion_cost, conversion_rate, form_cnt,
                        message_action_cnt, clue_message_count,
                        {', '.join(v15_cols)},
                        promotion_id, promotion_name, project_id, project_name,
                        raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {v15_placeholders}, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, material_id, stat_date)
                    DO UPDATE SET
                        material_name=excluded.material_name,
                        material_type=excluded.material_type,
                        stat_cost=excluded.stat_cost, show_cnt=excluded.show_cnt,
                        click_cnt=excluded.click_cnt, ctr=excluded.ctr,
                        cpc_platform=excluded.cpc_platform,
                        cpm_platform=excluded.cpm_platform,
                        convert_cnt=excluded.convert_cnt,
                        conversion_cost=excluded.conversion_cost,
                        conversion_rate=excluded.conversion_rate,
                        form_cnt=excluded.form_cnt,
                        message_action_cnt=excluded.message_action_cnt,
                        clue_message_count=excluded.clue_message_count,
                        {v15_update},
                        promotion_id=CASE WHEN excluded.promotion_id != ''
                            THEN excluded.promotion_id ELSE material_reports.promotion_id END,
                        promotion_name=CASE WHEN excluded.promotion_name != ''
                            THEN excluded.promotion_name ELSE material_reports.promotion_name END,
                        project_id=CASE WHEN excluded.project_id != ''
                            THEN excluded.project_id ELSE material_reports.project_id END,
                        project_name=CASE WHEN excluded.project_name != ''
                            THEN excluded.project_name ELSE material_reports.project_name END,
                        raw_data=excluded.raw_data
                    """,
                    (
                        str(account_id),
                        str(row.get("material_id", "")),
                        row.get("material_name", ""),
                        row.get("material_type", ""),
                        row.get("stat_time_day", row.get("stat_date", "")),
                        self._float(row, "stat_cost"),
                        self._int(row, "show_cnt"),
                        self._int(row, "click_cnt"),
                        self._float(row, "ctr"),
                        self._float(row, "cpc_platform"),
                        self._float(row, "cpm_platform"),
                        self._int(row, "convert_cnt"),
                        self._float(row, "conversion_cost"),
                        self._float(row, "conversion_rate"),
                        self._int(row, "form_cnt"),
                        self._int(row, "message_action_cnt"),
                        self._int(row, "clue_message_count"),
                        *v15_vals,
                        str(row.get("promotion_id", "")),
                        str(row.get("promotion_name", "")),
                        str(row.get("project_id", "")),
                        str(row.get("project_name", "")),
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )
                count += 1
            except Exception as e:
                logger.warning("Material upsert failed for %s: %s", account_id, e)

        conn.commit()
        return count

    # ── Promotion Reports ─────────────────────────────────────

    def upsert_promotion_reports(self, account_id: str, rows: list[dict]) -> int:
        """Insert/update promotion-level report rows."""
        conn = self._get_conn()
        count = 0
        v15_cols = self._v15_col_names()
        v15_placeholders = ", ".join(["?"] * len(v15_cols))
        v15_update = self._v15_update_clause()
        for row in rows:
            try:
                v15_vals = self._v15_row_values(row)
                conn.execute(
                    f"""
                    INSERT INTO promotion_reports (
                        account_id, promotion_id, promotion_name, promotion_status,
                        project_id, project_name,
                        local_life_shop_id, local_life_shop_name,
                        stat_date,
                        stat_cost, show_cnt, click_cnt, ctr,
                        cpc_platform, cpm_platform,
                        convert_cnt, conversion_cost, conversion_rate,
                        message_action_cnt, clue_message_count,
                        {', '.join(v15_cols)},
                        raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {v15_placeholders}, ?)
                    ON CONFLICT(account_id, promotion_id, stat_date)
                    DO UPDATE SET
                        promotion_name=excluded.promotion_name,
                        promotion_status=excluded.promotion_status,
                        project_id=excluded.project_id,
                        project_name=excluded.project_name,
                        local_life_shop_id=excluded.local_life_shop_id,
                        local_life_shop_name=excluded.local_life_shop_name,
                        stat_cost=excluded.stat_cost, show_cnt=excluded.show_cnt,
                        click_cnt=excluded.click_cnt, ctr=excluded.ctr,
                        cpc_platform=excluded.cpc_platform,
                        cpm_platform=excluded.cpm_platform,
                        convert_cnt=excluded.convert_cnt,
                        conversion_cost=excluded.conversion_cost,
                        conversion_rate=excluded.conversion_rate,
                        message_action_cnt=excluded.message_action_cnt,
                        clue_message_count=excluded.clue_message_count,
                        {v15_update},
                        raw_data=excluded.raw_data
                    """,
                    (
                        str(account_id),
                        str(row.get("promotion_id", "")),
                        row.get("promotion_name", ""),
                        row.get("promotion_status", ""),
                        row.get("project_id", ""),
                        row.get("project_name", ""),
                        row.get("local_life_shop_id", ""),
                        row.get("local_life_shop_name", ""),
                        row.get("stat_time_day", row.get("stat_date", "")),
                        self._float(row, "stat_cost"),
                        self._int(row, "show_cnt"),
                        self._int(row, "click_cnt"),
                        self._float(row, "ctr"),
                        self._float(row, "cpc_platform"),
                        self._float(row, "cpm_platform"),
                        self._int(row, "convert_cnt"),
                        self._float(row, "conversion_cost"),
                        self._float(row, "conversion_rate"),
                        self._int(row, "message_action_cnt"),
                        self._int(row, "clue_message_count"),
                        *v15_vals,
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )
                count += 1
            except Exception as e:
                logger.warning("Promotion upsert failed for %s/%s: %s",
                              account_id, row.get("promotion_id", "?"), e)

        conn.commit()
        return count

    # ── Project Reports ────────────────────────────────────────

    def upsert_project_reports(self, account_id: str, rows: list[dict]) -> int:
        """Insert/update project-level report rows."""
        conn = self._get_conn()
        count = 0
        v15_cols = self._v15_col_names()
        v15_placeholders = ", ".join(["?"] * len(v15_cols))
        v15_update = self._v15_update_clause()
        for row in rows:
            try:
                v15_vals = self._v15_row_values(row)
                conn.execute(
                    f"""
                    INSERT INTO project_reports (
                        account_id, project_id, project_name, stat_date,
                        stat_cost, show_cnt, click_cnt, ctr,
                        cpc_platform, cpm_platform,
                        convert_cnt, conversion_cost, conversion_rate,
                        message_action_cnt, clue_message_count,
                        {', '.join(v15_cols)},
                        raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {v15_placeholders}, ?)
                    ON CONFLICT(account_id, project_id, stat_date)
                    DO UPDATE SET
                        project_name=excluded.project_name,
                        stat_cost=excluded.stat_cost, show_cnt=excluded.show_cnt,
                        click_cnt=excluded.click_cnt, ctr=excluded.ctr,
                        cpc_platform=excluded.cpc_platform,
                        cpm_platform=excluded.cpm_platform,
                        convert_cnt=excluded.convert_cnt,
                        conversion_cost=excluded.conversion_cost,
                        conversion_rate=excluded.conversion_rate,
                        message_action_cnt=excluded.message_action_cnt,
                        clue_message_count=excluded.clue_message_count,
                        {v15_update},
                        raw_data=excluded.raw_data
                    """,
                    (
                        str(account_id),
                        str(row.get("project_id", "")),
                        row.get("project_name", ""),
                        row.get("stat_time_day", row.get("stat_date", "")),
                        self._float(row, "stat_cost"),
                        self._int(row, "show_cnt"),
                        self._int(row, "click_cnt"),
                        self._float(row, "ctr"),
                        self._float(row, "cpc_platform"),
                        self._float(row, "cpm_platform"),
                        self._int(row, "convert_cnt"),
                        self._float(row, "conversion_cost"),
                        self._float(row, "conversion_rate"),
                        self._int(row, "message_action_cnt"),
                        self._int(row, "clue_message_count"),
                        *v15_vals,
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )
                count += 1
            except Exception as e:
                logger.warning("Project upsert failed for %s/%s: %s",
                              account_id, row.get("project_id", "?"), e)

        conn.commit()
        return count

    def get_material_reports(
        self,
        account_id: str | None = None,
        material_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Query material-level reports with optional filters."""
        conn = self._get_conn()
        conditions = []
        params: list = []
        if account_id:
            conditions.append("account_id = ?")
            params.append(account_id)
        if material_id:
            conditions.append("material_id = ?")
            params.append(material_id)
        if start_date:
            conditions.append("stat_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("stat_date <= ?")
            params.append(end_date)

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM material_reports WHERE {where} ORDER BY stat_cost DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_material_summary(
        self, date_str: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """
        Get material-level summary.

        Use exactly one of:
          - date_str: single date (original behaviour)
          - start_date + end_date: aggregate over date range
        """
        conn = self._get_conn()

        if start_date and end_date:
            where = "m.stat_date >= ? AND m.stat_date <= ?"
            params = (start_date, end_date)
        elif date_str:
            where = "m.stat_date = ?"
            params = (date_str,)
        else:
            # Default: latest date
            latest = self.get_latest_date("material_reports")
            where = "m.stat_date = ?"
            params = (latest,)

        rows = conn.execute(
            f"""
            SELECT
                m.material_id, m.material_name, m.material_type,
                m.account_id, a.name as account_name,
                SUM(m.stat_cost) as total_cost,
                SUM(m.show_cnt) as total_show,
                SUM(m.click_cnt) as total_click,
                SUM(m.convert_cnt) as total_convert,
                SUM(m.message_action_cnt) as total_consult,
                SUM(m.clue_message_count) as total_clue,
                CASE WHEN SUM(m.show_cnt) > 0
                    THEN ROUND(SUM(m.click_cnt)*100.0/SUM(m.show_cnt), 2) END as ctr,
                CASE WHEN SUM(m.convert_cnt) > 0 AND SUM(m.stat_cost) > 0
                    THEN ROUND(SUM(m.stat_cost)/SUM(m.convert_cnt), 2) END as cpa,
                CASE WHEN SUM(m.clue_message_count) > 0 AND SUM(m.stat_cost) > 0
                    THEN ROUND(SUM(m.stat_cost)/SUM(m.clue_message_count), 2) END as lead_cpa,
                -- Attribution fields (v1.6): take most common non-empty value
                MAX(m.promotion_id) as promotion_id,
                MAX(CASE WHEN m.promotion_id != '' THEN m.promotion_name END) as promotion_name,
                MAX(m.project_id) as project_id,
                MAX(CASE WHEN m.project_id != '' THEN m.project_name END) as project_name
            FROM material_reports m
            LEFT JOIN accounts a ON m.account_id = a.account_id
            WHERE {where}
            GROUP BY m.material_id
            ORDER BY SUM(m.stat_cost) DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_material_ranking(
        self,
        start_date: str,
        end_date: str,
        top_n: int = 15,
    ) -> list[dict]:
        """Rank materials by total cost in a date range, across all accounts."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT
                m.material_id, MAX(m.material_name) as material_name,
                MAX(m.material_type) as material_type,
                m.account_id, a.name as account_name,
                SUM(m.stat_cost) as total_cost,
                SUM(m.show_cnt) as total_show,
                SUM(m.click_cnt) as total_click,
                SUM(m.convert_cnt) as total_convert,
                SUM(m.message_action_cnt) as total_consult,
                SUM(m.clue_message_count) as total_clue,
                CASE WHEN SUM(m.show_cnt) > 0
                    THEN ROUND(SUM(m.click_cnt)*100.0/SUM(m.show_cnt), 2) END as ctr,
                CASE WHEN SUM(m.convert_cnt) > 0 AND SUM(m.stat_cost) > 0
                    THEN ROUND(SUM(m.stat_cost)/SUM(m.convert_cnt), 2) END as cpa,
                CASE WHEN SUM(m.clue_message_count) > 0 AND SUM(m.stat_cost) > 0
                    THEN ROUND(SUM(m.stat_cost)/SUM(m.clue_message_count), 2) END as lead_cpa,
                MAX(CASE WHEN m.promotion_id != '' THEN m.promotion_id END) as promotion_id,
                MAX(CASE WHEN m.promotion_id != '' THEN m.promotion_name END) as promotion_name,
                MAX(CASE WHEN m.project_id != '' THEN m.project_id END) as project_id,
                MAX(CASE WHEN m.project_id != '' THEN m.project_name END) as project_name
            FROM material_reports m
            LEFT JOIN accounts a ON m.account_id = a.account_id
            WHERE m.stat_date BETWEEN ? AND ?
            GROUP BY m.material_id
            ORDER BY SUM(m.stat_cost) DESC
            LIMIT ?
            """,
            (start_date, end_date, top_n),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_account_material_summary(
        self, account_id: str, date_str: str
    ) -> dict:
        """Get material summary for a specific account on a specific date."""
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT material_id) as material_count,
                SUM(stat_cost) as total_cost,
                SUM(show_cnt) as total_show,
                SUM(click_cnt) as total_click,
                SUM(convert_cnt) as total_convert,
                SUM(message_action_cnt) as total_consult,
                SUM(clue_message_count) as total_clue,
                CASE WHEN SUM(show_cnt) > 0
                    THEN ROUND(SUM(click_cnt)*100.0/SUM(show_cnt), 2) END as ctr
            FROM material_reports
            WHERE account_id = ? AND stat_date = ?
            """,
            (str(account_id), date_str),
        ).fetchone()
        return dict(row) if row else {}

    def get_zero_performance_materials(self, date_str: str) -> list[dict]:
        """Find materials with cost > 0 but zero conversions/consultations."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT m.*, a.name as account_name
            FROM material_reports m
            LEFT JOIN accounts a ON m.account_id = a.account_id
            WHERE m.stat_date = ?
              AND m.stat_cost > 0
              AND m.message_action_cnt = 0
              AND m.clue_message_count = 0
              AND m.convert_cnt = 0
            ORDER BY m.stat_cost DESC
            LIMIT 20
            """,
            (date_str,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Optimization Log ───────────────────────────────────────

    def log_optimization(
        self,
        account_id: str,
        rule_name: str,
        condition_met: str,
        suggestion: str,
        promotion_id: str = "",
        action_taken: str = "",
        metrics_snapshot: dict | None = None,
    ):
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO optimization_log
                (account_id, promotion_id, rule_name, condition_met,
                 suggestion, action_taken, metrics_snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(account_id), promotion_id, rule_name,
                condition_met, suggestion, action_taken,
                json.dumps(metrics_snapshot or {}, ensure_ascii=False),
            ),
        )
        conn.commit()

    def get_optimization_history(
        self, account_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        conn = self._get_conn()
        conditions = []
        params: list = []
        if account_id:
            conditions.append("account_id = ?")
            params.append(account_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM optimization_log WHERE {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in conn.execute(query, params).fetchall()]

    def close(self):
        pass  # Connections are created per-call, no persistent connection to close

    def get_latest_date(self, table: str = "material_reports") -> str | None:
        """Get the most recent date with data in a table."""
        conn = self._get_conn()
        row = conn.execute(
            f"SELECT MAX(stat_date) as latest FROM {table}"
        ).fetchone()
        return row["latest"] if row else None
