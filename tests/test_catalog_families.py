import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from catalog.families import load_curated_families


class TestLoadCuratedFamilies(unittest.TestCase):
    def test_loads_list_of_families(self):
        families = load_curated_families()
        self.assertIsInstance(families, list)
        self.assertGreater(len(families), 0)

    def test_every_family_has_required_shape(self):
        for fam in load_curated_families():
            self.assertIn("name", fam)
            self.assertIn("openrouter_match", fam)
            self.assertIsInstance(fam["openrouter_match"], list)
            self.assertIn("ollama_variants", fam)
            self.assertGreater(len(fam["ollama_variants"]), 0)
            for variant in fam["ollama_variants"]:
                self.assertIn("tag", variant)
                self.assertIn("size_gb", variant)
                self.assertIn("min_ram_gb", variant)
                self.assertIn("min_vram_gb", variant)

    def test_known_families_present(self):
        # phi-4 and mistral-small were dropped from the starter list: OpenRouter
        # only benchmarks their full/flagship cloud sizes (14B+ / 22B+), which
        # would misrepresent the much smaller local Ollama tags (phi4-mini 3.8B,
        # mistral 7B) this project actually installs. Keep only families where
        # the curated tag is a fair size match to what gets benchmarked.
        names = {f["name"] for f in load_curated_families()}
        for expected in ("qwen2.5", "gemma-3", "llama-3.2"):
            self.assertIn(expected, names, f"expected family '{expected}' in allowlist")

    def test_family_openrouter_match_is_consistent_with_its_own_tags(self):
        # Regression test for a real bug: a family named/matched "llama-3.3"
        # pointed at an actual llama3.2 Ollama tag - a different model
        # generation, not just a size variant. Every family's name should at
        # least share its version string with what its openrouter_match list
        # searches for, so a future hand-edit can't silently reintroduce this.
        for fam in load_curated_families():
            self.assertTrue(
                any(fam["name"] in m or m in fam["name"] for m in fam["openrouter_match"]),
                f"family '{fam['name']}' openrouter_match {fam['openrouter_match']} "
                f"doesn't obviously correspond to its own name",
            )
