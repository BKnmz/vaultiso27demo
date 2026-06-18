"""
Tests for the optional generation extras: structure exemplars + guidance RAG.
Both must be fail-soft and OFF by default. No Ollama, no live ChromaDB.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pipeline


EXEMPLAR_DIR = Path(__file__).parent.parent / "rag" / "exemplars"


class TestStructureExemplar(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(pipeline.get_structure_exemplar({}, "4.3"), "")

    def test_off_when_flag_false(self):
        cfg = {"generation": {"use_structure_exemplars": False}}
        self.assertEqual(pipeline.get_structure_exemplar(cfg, "4.3"), "")

    def test_returns_block_when_enabled_and_present(self):
        cfg = {"generation": {"use_structure_exemplars": True}}
        block = pipeline.get_structure_exemplar(cfg, "4.3")
        self.assertIn("FORMAT EXAMPLE", block)
        self.assertIn("#", block)  # contains markdown headings

    def test_missing_exemplar_returns_empty(self):
        cfg = {"generation": {"use_structure_exemplars": True}}
        self.assertEqual(pipeline.get_structure_exemplar(cfg, "9.9"), "")


class TestExemplarSkeletonsAreHeadingsOnly(unittest.TestCase):
    def test_no_long_body_paragraphs(self):
        for md in EXEMPLAR_DIR.glob("*.md"):
            for line in md.read_text(encoding="utf-8").splitlines():
                self.assertLessEqual(
                    len(line), 120,
                    f"{md.name} has a long line (looks like body text, not a heading): {line[:60]}...",
                )

    def test_mostly_headings(self):
        for md in EXEMPLAR_DIR.glob("*.md"):
            lines = [ln for ln in md.read_text(encoding="utf-8").splitlines() if ln.strip()]
            headings = [ln for ln in lines if ln.lstrip().startswith("#")]
            self.assertEqual(len(headings), len(lines),
                             f"{md.name} contains non-heading content lines")


class TestGuidanceRagFailSoft(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(pipeline.get_guidance_context({"rag": {}}, None, "4.3"), "")

    def test_off_when_flag_false(self):
        cfg = {"rag": {"use_guidance_rag": False}}
        self.assertEqual(pipeline.get_guidance_context(cfg, None, "4.3"), "")


if __name__ == "__main__":
    unittest.main()
