"""
Tests for QualityRadar — battle list and scoring.
"""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.analysis.quality_radar import QualityRadar
from src.pipeline.storage import Storage


class TestQualityRadar(unittest.TestCase):
    """Test QualityRadar on a temp database."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, 'test.db')
        # Create schema first using Storage
        self.storage = Storage(db_path=self.db_path)
        self.radar = QualityRadar(db_path=self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_battle_list_empty_db_returns_empty(self):
        result = self.radar.battle_list()
        self.assertIn('window', result)
        self.assertIsNone(result['window'])

    def test_battle_list_with_data(self):
        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        conn = self.radar._conn()
        conn.execute("INSERT INTO accounts (account_id, name) VALUES ('a1', 'Test')")
        conn.execute("""
            INSERT INTO account_reports
            (account_id, stat_date, stat_cost, show_cnt, click_cnt,
             message_action_cnt, clue_message_count, delivery_type)
            VALUES ('a1', ?, 1000, 10000, 500, 20, 10, 'total')
        """, (yesterday,))
        conn.execute("""
            INSERT INTO material_reports
            (material_id, account_id, stat_date, stat_cost, show_cnt, click_cnt,
             message_action_cnt, clue_message_count)
            VALUES ('m1', 'a1', ?, 500, 5000, 200, 10, 5)
        """, (yesterday,))
        conn.commit()

        result = self.radar.battle_list()
        self.assertIn('window', result)
        self.assertNotEqual(result['window'], None)
        self.assertIn('scale_up', result)
        self.assertIn('cut_down', result)
        self.assertIn('fatigue', result)
        self.assertIn('traps', result)
        self.assertIn('check', result)
        self.assertIsInstance(result['scale_up'], list)

    def test_init_with_default_db(self):
        r = QualityRadar()
        self.assertIsNotNone(r.db_path)


if __name__ == '__main__':
    unittest.main()
