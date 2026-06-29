"""
Tests for MaterialDecisionEngine — four-quadrant classification and scoring.
"""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pipeline.storage import Storage
from src.analysis.material_decision import MaterialDecisionEngine


class TestMaterialDecisionEngine(unittest.TestCase):
    """Test material decision engine logic on a temp database."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, 'test.db')
        self.storage = Storage(db_path=self.db_path)
        self.engine = MaterialDecisionEngine(storage=self.storage)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_database_returns_empty(self):
        result = self.engine.analyze()
        self.assertIn('decision_matrix', result)
        self.assertEqual(len(result['decision_matrix']), 0)
        self.assertIn('quadrant_summary', result)

    def test_with_minimal_data(self):
        """Engine should not crash with minimal data."""
        self.storage.ensure_account('test1', 'Test Account')
        today = date.today().strftime('%Y-%m-%d')
        self.storage.upsert_account_reports('test1', [{
            'advertiser_id': 'test1',
            'stat_datetime': today,
            'stat_cost': 1000.0,
            'show_cnt': 10000,
            'delivery_type': 'total',
        }])

        result = self.engine.analyze()
        self.assertIn('decision_matrix', result)
        self.assertIn('quadrant_summary', result)
        self.assertIn('suggestions', result)

    def test_quadrant_summary_has_all_keys(self):
        """Quadrant summary should have all 5 categories."""
        self.storage.ensure_account('test2', 'Test2')
        today = date.today().strftime('%Y-%m-%d')
        self.storage.upsert_account_reports('test2', [{
            'advertiser_id': 'test2',
            'stat_datetime': today,
            'stat_cost': 500.0,
            'show_cnt': 1000,
            'delivery_type': 'total',
        }])

        result = self.engine.analyze()
        expected_keys = {'star', 'potential', 'watch', 'stop', 'insufficient'}
        summary = result['quadrant_summary']
        for key in expected_keys:
            self.assertIn(key, summary,
                          f"quadrant_summary missing key: {key}, has: {list(summary.keys())}")


if __name__ == '__main__':
    unittest.main()
