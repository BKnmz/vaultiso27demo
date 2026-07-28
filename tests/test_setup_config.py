"""
Tests for setup_config.py — tier selection (VRAM-fit-first OR logic) and
the LEGACY_FACTORY_MODELS migration set. No hardware probing, no LLM calls.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import setup_config


def _tier(ram, vram):
    return setup_config.select_tier({"ram_gb": ram, "vram_gb": vram})["name"]


class TestSelectTier(unittest.TestCase):
    def test_high_needs_12gb_vram(self):
        self.assertEqual(_tier(64, 16), "high")

    def test_mid_on_6_to_12gb_vram(self):
        self.assertEqual(_tier(16, 8), "mid")

    def test_cpu_rich_when_ram_high_vram_small(self):
        # The old AND-coupling bug sent this to "low"; OR logic keeps it cpu_rich.
        self.assertEqual(_tier(20, 2), "cpu_rich")

    def test_cpu_rich_with_no_gpu(self):
        self.assertEqual(_tier(32, 0), "cpu_rich")

    def test_low_on_modest_ram(self):
        self.assertEqual(_tier(8, 0), "low")

    def test_minimal_on_tiny_ram(self):
        self.assertEqual(_tier(4, 0), "minimal")

    def test_no_gpu_forces_num_gpu_zero(self):
        t = setup_config.select_tier({"ram_gb": 32, "vram_gb": 0})
        self.assertEqual(t["num_gpu"], 0)

    def test_this_machine_resolves_to_phi4(self):
        # Documented dev machine: 20 GB RAM / 2 GB VRAM -> cpu_rich -> phi4-mini.
        t = setup_config.select_tier({"ram_gb": 19.8, "vram_gb": 2.0})
        self.assertEqual(t["gen_model"], "phi4-mini:3.8b-q4_K_M")
        self.assertEqual(t["reviewer_model"], "qwen2.5:1.5b")


class TestLegacyFactoryModels(unittest.TestCase):
    def test_current_tier_models_are_migratable(self):
        for tier in setup_config.TIERS:
            self.assertIn(tier["gen_model"], setup_config.LEGACY_FACTORY_MODELS)
            self.assertIn(tier["reviewer_model"], setup_config.LEGACY_FACTORY_MODELS)

    def test_v041_gemma_tags_included(self):
        # So a v0.4.1 install migrates back on re-detection.
        self.assertIn("gemma4:e2b-it-qat", setup_config.LEGACY_FACTORY_MODELS)


class TestTierOutputLengthFields(unittest.TestCase):
    """F2: every tier must declare num_predict and length_profile."""

    def test_all_tiers_have_num_predict(self):
        for tier in setup_config.TIERS:
            self.assertIn("num_predict", tier, f"Tier '{tier['name']}' missing num_predict")
            self.assertIsInstance(tier["num_predict"], int)
            self.assertGreater(tier["num_predict"], 0)

    def test_all_tiers_have_length_profile(self):
        for tier in setup_config.TIERS:
            self.assertIn("length_profile", tier, f"Tier '{tier['name']}' missing length_profile")
            self.assertIsInstance(tier["length_profile"], str)
            self.assertTrue(tier["length_profile"].strip())

    def test_high_and_mid_have_larger_num_predict(self):
        # GPU tiers should produce longer docs than CPU-only tiers.
        high_np = next(t["num_predict"] for t in setup_config.TIERS if t["name"] == "high")
        minimal_np = next(t["num_predict"] for t in setup_config.TIERS if t["name"] == "minimal")
        self.assertGreater(high_np, minimal_np)


class TestApplyToConfigWritesNumPredict(unittest.TestCase):
    """F2: apply_to_config() must write llm.num_predict and pipeline.target_words."""

    def test_apply_writes_llm_num_predict(self):
        import tempfile, copy
        import yaml

        # Build a minimal in-memory config similar to a fresh install
        base_cfg = {
            "llm": {"base_url": "http://localhost:11434", "model": "phi4-mini:3.8b-q4_K_M",
                    "temperature": 0.2, "num_gpu": 1},
            "critic": {"model": "qwen2.5:1.5b"},
            "timeouts": {},
            "pipeline": {"clauses": []},
            "rag": {},
            "paths": {},
            "export": {},
            "github": {},
        }

        hw = {"ram_gb": 20, "vram_gb": 2, "cpu": "TestCPU", "os": "TestOS"}
        tier = setup_config.select_tier(hw)

        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                        delete=False, encoding="utf-8") as f:
            yaml.dump(base_cfg, f)
            tmp_path = Path(f.name)

        # Temporarily redirect CONFIG_PATH
        original_path = setup_config.CONFIG_PATH
        setup_config.CONFIG_PATH = tmp_path
        try:
            setup_config.apply_to_config(hw, tier)
            result = yaml.safe_load(tmp_path.read_text(encoding="utf-8"))
        finally:
            setup_config.CONFIG_PATH = original_path
            tmp_path.unlink(missing_ok=True)

        self.assertIn("num_predict", result["llm"])
        self.assertEqual(result["llm"]["num_predict"], tier["num_predict"])
        self.assertIn("target_words", result["pipeline"])
        self.assertEqual(result["pipeline"]["target_words"], tier["length_profile"])


class TestItemCountsStructure(unittest.TestCase):
    """Every tier must have an item_counts dict with all required keys."""

    def test_all_tiers_have_item_counts(self):
        required_keys = {"min_risks", "risk_range", "min_objectives", "obj_range",
                         "min_metrics", "metric_range", "min_improvements", "table_note"}
        for tier in setup_config.TIERS:
            self.assertIn("item_counts", tier, f"Tier {tier['name']} missing item_counts")
            missing = required_keys - set(tier["item_counts"].keys())
            self.assertEqual(missing, set(), f"Tier {tier['name']} missing keys: {missing}")

    def test_small_tiers_have_smaller_counts(self):
        """cpu_rich/low/minimal tiers must have min_risks < high/mid tiers."""
        small_names = {"cpu_rich", "low", "minimal"}
        large_names = {"high", "mid"}
        small_min = min(t["item_counts"]["min_risks"] for t in setup_config.TIERS if t["name"] in small_names)
        large_min = min(t["item_counts"]["min_risks"] for t in setup_config.TIERS if t["name"] in large_names)
        self.assertLess(small_min, large_min)

    def test_apply_to_config_writes_item_counts(self):
        """apply_to_config must write generation.item_counts to config.yaml."""
        import tempfile
        import shutil
        import yaml

        tmpdir = Path(tempfile.mkdtemp())
        try:
            src = Path(setup_config.CONFIG_PATH)
            dst = tmpdir / "config.yaml"
            shutil.copy(src, dst)
            orig_path = setup_config.CONFIG_PATH
            setup_config.CONFIG_PATH = dst
            try:
                hw = {"ram_gb": 20, "vram_gb": 2.0, "cpu": "test"}
                tier = setup_config.select_tier(hw)
                setup_config.apply_to_config(hw, tier)
                with open(dst) as f:
                    cfg = yaml.safe_load(f)
                self.assertIn("item_counts", cfg.get("generation", {}))
                self.assertIn("min_risks", cfg["generation"]["item_counts"])
            finally:
                setup_config.CONFIG_PATH = orig_path
        finally:
            shutil.rmtree(tmpdir)


class TestModelsCatalogFile(unittest.TestCase):
    """The bundled models_catalog.json is the source of truth for gen_model/
    reviewer_model/label/why/speed — TIERS merges it at import time with the
    Python-side hardware-tuning fields (min_ram_gb, min_vram_gb, timeouts, etc.)."""

    def test_bundled_catalog_has_all_five_tiers(self):
        catalog = setup_config.load_models_catalog()
        self.assertEqual(
            set(catalog["tiers"].keys()),
            {"high", "mid", "cpu_rich", "low", "minimal"},
        )

    def test_bundled_catalog_tier_entries_have_required_keys(self):
        catalog = setup_config.load_models_catalog()
        required = {"gen_model", "reviewer_model", "label", "why", "speed"}
        for name, entry in catalog["tiers"].items():
            missing = required - set(entry.keys())
            self.assertEqual(missing, set(), f"catalog tier '{name}' missing keys: {missing}")

    def test_bundled_catalog_has_legacy_tags(self):
        catalog = setup_config.load_models_catalog()
        self.assertIn("legacy_tags", catalog)
        self.assertIn("gemma4:e2b-it-qat", catalog["legacy_tags"])

    def test_tiers_merged_from_catalog_keep_full_shape(self):
        # Every tier dict must still carry both the catalog fields AND the
        # Python-side tuning fields — same contract downstream code relies on.
        for tier in setup_config.TIERS:
            for key in ("gen_model", "reviewer_model", "label", "why", "speed",
                        "min_ram_gb", "min_vram_gb", "ollama_timeout",
                        "model_swap_delay", "num_predict", "item_counts"):
                self.assertIn(key, tier, f"tier '{tier.get('name')}' missing '{key}' after merge")

    def test_legacy_factory_models_derived_from_catalog(self):
        catalog = setup_config.load_models_catalog()
        expected = set(catalog["legacy_tags"])
        for tier in catalog["tiers"].values():
            expected.add(tier["gen_model"])
            expected.add(tier["reviewer_model"])
        self.assertEqual(setup_config.LEGACY_FACTORY_MODELS, expected)


if __name__ == "__main__":
    unittest.main()
