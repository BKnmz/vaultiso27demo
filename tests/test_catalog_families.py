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
        names = {f["name"] for f in load_curated_families()}
        for expected in ("phi-4", "qwen2.5", "gemma-3", "llama-3.3", "mistral-small"):
            self.assertIn(expected, names, f"expected family '{expected}' in allowlist")
