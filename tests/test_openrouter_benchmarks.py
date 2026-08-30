import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from catalog.openrouter_benchmarks import fetch_benchmarks, rank_candidates
from catalog.families import load_curated_families


FAKE_RESPONSE = {
    "data": [
        {"model_permaslug": "microsoft/phi-4", "display_name": "Phi 4", "intelligence_index": 42.1},
        {"model_permaslug": "qwen/qwen2.5-7b-instruct", "display_name": "Qwen2.5 7B Instruct", "intelligence_index": 35.0},
        {"model_permaslug": "qwen/qwen2.5-1.5b-instruct", "display_name": "Qwen2.5 1.5B Instruct", "intelligence_index": 18.2},
        {"model_permaslug": "unrelated/some-other-model", "display_name": "Some Other Model", "intelligence_index": 99.9},
    ]
}


class TestFetchBenchmarks(unittest.TestCase):
    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key-123"})
    @patch("catalog.openrouter_benchmarks.requests.get")
    def test_fetch_returns_data_rows(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = FAKE_RESPONSE
        mock_get.return_value = mock_resp

        rows = fetch_benchmarks()
        self.assertEqual(len(rows), 4)

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key-123"})
    @patch("catalog.openrouter_benchmarks.requests.get")
    def test_fetch_sends_bearer_auth_header(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = FAKE_RESPONSE
        mock_get.return_value = mock_resp

        fetch_benchmarks()
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key-123")

    @patch.dict("os.environ", {}, clear=True)
    def test_fetch_raises_without_api_key(self):
        # Auth is required by OpenRouter's benchmarks endpoint - fail fast with a
        # clear message rather than sending an unauthenticated request that 401s.
        with self.assertRaises(RuntimeError):
            fetch_benchmarks()

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key-123"})
    @patch("catalog.openrouter_benchmarks.requests.get")
    def test_fetch_raises_on_non_200(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        with self.assertRaises(RuntimeError):
            fetch_benchmarks()

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key-123"})
    @patch("catalog.openrouter_benchmarks.requests.get")
    def test_fetch_raises_on_timeout(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()
        with self.assertRaises(requests.exceptions.Timeout):
            fetch_benchmarks()


class TestRankCandidates(unittest.TestCase):
    def setUp(self):
        self.families = load_curated_families()

    def test_ranks_by_intelligence_index_descending(self):
        ranked = rank_candidates(self.families, FAKE_RESPONSE["data"],
                                  tier_min_ram_gb=0, tier_min_vram_gb=0)
        scores = [c["intelligence_index"] for c in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_excludes_unmatched_models(self):
        ranked = rank_candidates(self.families, FAKE_RESPONSE["data"],
                                  tier_min_ram_gb=0, tier_min_vram_gb=0)
        tags = {c["tag"] for c in ranked}
        # "unrelated/some-other-model" (99.9, highest score) must never appear -
        # it matches no curated family.
        self.assertTrue(all(t in {"phi4-mini:3.8b-q4_K_M", "qwen2.5:7b-instruct-q4_K_M",
                                   "qwen2.5:1.5b"} for t in tags))

    def test_filters_variants_that_dont_fit_tier(self):
        # minimal tier: 0 RAM/VRAM floor - only the 1.5b qwen variant qualifies
        # among the two qwen2.5 variants (7b needs 8 RAM / 6 VRAM).
        ranked = rank_candidates(self.families, FAKE_RESPONSE["data"],
                                  tier_min_ram_gb=0, tier_min_vram_gb=0)
        qwen_tags = {c["tag"] for c in ranked if c["family"] == "qwen2.5"}
        self.assertIn("qwen2.5:1.5b", qwen_tags)
        self.assertNotIn("qwen2.5:7b-instruct-q4_K_M", qwen_tags)

    def test_gpu_tier_does_not_exclude_variants_on_ram_alone(self):
        # "high" tier: min_vram_gb=12, min_ram_gb=0 (RAM isn't the constraint -
        # a 12GB+ VRAM machine is assumed to have adequate RAM). A curated
        # variant needing 8 GB RAM must NOT be excluded just because the tier's
        # own min_ram_gb floor is 0 - that 0 means "not gated on RAM", not
        # "0 GB of RAM guaranteed". Regression test for a real bug caught by
        # code-review: this previously excluded almost every GPU-tier variant.
        ranked = rank_candidates(self.families, FAKE_RESPONSE["data"],
                                  tier_min_ram_gb=0, tier_min_vram_gb=12)
        tags = {c["tag"] for c in ranked}
        # qwen2.5:7b-instruct-q4_K_M needs 8 GB RAM / 6 GB VRAM - fits a
        # 12GB-VRAM tier easily, and must not be excluded by the tier's own
        # min_ram_gb=0 (that means "not RAM-gated", not "0 GB guaranteed").
        self.assertIn("qwen2.5:7b-instruct-q4_K_M", tags)

    def test_ram_gated_tier_still_excludes_variants_needing_more_ram(self):
        ranked = rank_candidates(self.families, FAKE_RESPONSE["data"],
                                  tier_min_ram_gb=0, tier_min_vram_gb=0)
        qwen_tags = {c["tag"] for c in ranked if c["family"] == "qwen2.5"}
        self.assertNotIn("qwen2.5:7b-instruct-q4_K_M", qwen_tags)

    def test_caps_at_three_results(self):
        many_rows = [{"model_permaslug": f"microsoft/phi-4-v{i}", "display_name": "Phi 4",
                       "intelligence_index": float(i)} for i in range(10)]
        ranked = rank_candidates(self.families, many_rows,
                                  tier_min_ram_gb=0, tier_min_vram_gb=0)
        self.assertLessEqual(len(ranked), 3)


if __name__ == "__main__":
    unittest.main()
