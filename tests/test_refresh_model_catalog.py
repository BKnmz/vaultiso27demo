import sys
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from catalog.refresh_model_catalog import refresh, _is_stale


class TestIsStale(unittest.TestCase):
    def test_missing_timestamp_is_stale(self):
        self.assertTrue(_is_stale(None))

    def test_recent_timestamp_not_stale(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertFalse(_is_stale(recent))

    def test_old_timestamp_is_stale(self):
        old = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
        self.assertTrue(_is_stale(old))

    def test_boundary_89_days_not_stale(self):
        boundary = (datetime.now(timezone.utc) - timedelta(days=89)).isoformat()
        self.assertFalse(_is_stale(boundary))


class TestRefresh(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.catalog_path = self.tmpdir / "model_catalog.json"
        self.md_path = self.tmpdir / "MODEL_CATALOG.md"
        base = {
            "catalog_version": "2026.07",
            "tiers": {
                "minimal": {"gen_model": "qwen2.5:1.5b", "reviewer_model": "qwen2.5:1.5b",
                            "label": "Minimal (< 8 GB RAM, CPU-only)",
                            "why": "test", "speed": "test"},
            },
            "legacy_tags": ["qwen2.5:1.5b"],
        }
        self.catalog_path.write_text(json.dumps(base), encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("catalog.refresh_model_catalog.fetch_benchmarks")
    def test_writes_benchmark_choices_and_timestamp_on_success(self, mock_fetch):
        mock_fetch.return_value = [
            {"model_permaslug": "qwen/qwen2.5-1.5b-instruct", "display_name": "Qwen2.5 1.5B",
             "intelligence_index": 18.2},
        ]
        result = refresh(force=True, catalog_path=self.catalog_path, md_path=self.md_path)
        self.assertTrue(result)
        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        self.assertIn("fetched_at", data)
        self.assertIn("benchmark_choices", data["tiers"]["minimal"])
        self.assertTrue(self.md_path.exists())

    @patch("catalog.refresh_model_catalog.fetch_benchmarks")
    def test_leaves_cache_untouched_on_fetch_failure(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("network down")
        before = self.catalog_path.read_text(encoding="utf-8")
        result = refresh(force=True, catalog_path=self.catalog_path, md_path=self.md_path)
        self.assertFalse(result)
        after = self.catalog_path.read_text(encoding="utf-8")
        self.assertEqual(before, after)

    @patch("catalog.refresh_model_catalog.fetch_benchmarks")
    def test_skips_fetch_when_cache_fresh_and_not_forced(self, mock_fetch):
        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        data["fetched_at"] = datetime.now(timezone.utc).isoformat()
        self.catalog_path.write_text(json.dumps(data), encoding="utf-8")

        result = refresh(force=False, catalog_path=self.catalog_path, md_path=self.md_path)
        self.assertFalse(result)
        mock_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
