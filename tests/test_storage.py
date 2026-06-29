"""
Tests for Storage — SQLite schema creation, upserts, queries.
"""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pipeline.storage import Storage


class TestStorage(unittest.TestCase):
    """Test Storage operations on a temp database."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, 'test.db')
        self.storage = Storage(db_path=self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_schema_creates_all_tables(self):
        conn = self.storage._get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r['name'] for r in tables}
        expected = {'accounts', 'account_reports', 'promotion_reports',
                     'material_reports', 'optimization_log'}
        for t in expected:
            self.assertIn(t, table_names, f"Table {t} should exist")

    def test_ensure_account(self):
        self.storage.ensure_account('acc1', 'Test Account')
        conn = self.storage._get_conn()
        row = conn.execute("SELECT * FROM accounts WHERE account_id='acc1'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['name'], 'Test Account')

    def test_upsert_account_reports(self):
        today = date.today().strftime('%Y-%m-%d')
        self.storage.upsert_account_reports('acc1', [{
            'advertiser_id': 'acc1',
            'stat_datetime': today,
            'stat_cost': 1000.0,
            'show_cnt': 10000,
            'delivery_type': 'total',
        }])
        conn = self.storage._get_conn()
        row = conn.execute(
            "SELECT * FROM account_reports WHERE account_id='acc1'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['stat_cost'], 1000.0)

    def test_get_latest_date_empty(self):
        result = self.storage.get_latest_date('material_reports')
        self.assertIsNone(result)

    def test_get_latest_date_with_data(self):
        today = date.today().strftime('%Y-%m-%d')
        conn = self.storage._get_conn()
        conn.execute("""
            INSERT INTO material_reports (material_id, account_id, stat_date, stat_cost, show_cnt, click_cnt)
            VALUES ('m1', 'a1', ?, 100, 1000, 50)
        """, (today,))
        conn.commit()
        result = self.storage.get_latest_date('material_reports')
        self.assertEqual(result, today)


if __name__ == '__main__':
    unittest.main()
