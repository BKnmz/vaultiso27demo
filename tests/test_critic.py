"""
Tests for critic.py — assessment parsing, CLAUSE_FOCUS completeness, prompt rendering, mock Ollama.
No real LLM calls.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import critic


SAMPLE_ORG = {
    "name": "Test Corp",
    "industry": "Testing",
    "size": "10 employees",
    "scope": "Test scope",
    "legal_basis": ["GDPR"],
}

PASS_OUTPUT = """## Critic Review — Clause 4.3: Scope

**Overall Assessment:** PASS
**Confidence:** HIGH

### Findings Table
| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | ISO Mapping | PASS | All mandatory elements present |
| 2 | Completeness | PASS | All sections present |
| 3 | Org Specificity | PASS | Specific to org |
| 4 | Internal Consistency | PASS | No contradictions |
| 5 | Audit Readiness | PASS | Ready for audit |

### Required Revisions
None — document meets requirements.

### Auditor Verdict
This document would pass a Stage 2 audit.
"""

CONDITIONAL_OUTPUT = """**Overall Assessment:** CONDITIONAL PASS
Some issues found.
"""

FAIL_OUTPUT = """**Overall Assessment:** FAIL
Critical issues found.
"""


class TestParseOverallAssessment(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(critic.parse_overall_assessment(PASS_OUTPUT), "PASS")

    def test_conditional_pass(self):
        self.assertEqual(critic.parse_overall_assessment(CONDITIONAL_OUTPUT), "CONDITIONAL PASS")

    def test_fail(self):
        self.assertEqual(critic.parse_overall_assessment(FAIL_OUTPUT), "FAIL")

    def test_unknown_when_no_marker(self):
        self.assertEqual(critic.parse_overall_assessment("No assessment here."), "UNKNOWN")

    def test_case_insensitive(self):
        text = "**Overall Assessment:** pass"
        self.assertEqual(critic.parse_overall_assessment(text), "PASS")


class TestClauseFocusCompleteness(unittest.TestCase):
    def test_all_clause_names_have_focus(self):
        missing = [cid for cid in critic.CLAUSE_NAMES if cid not in critic.CLAUSE_FOCUS]
        self.assertEqual(missing, [], f"CLAUSE_FOCUS missing entries for: {missing}")

    def test_no_orphan_focus_keys(self):
        extra = [cid for cid in critic.CLAUSE_FOCUS if cid not in critic.CLAUSE_NAMES]
        self.assertEqual(extra, [], f"CLAUSE_FOCUS has keys not in CLAUSE_NAMES: {extra}")

    def test_focus_strings_non_empty(self):
        for cid, focus in critic.CLAUSE_FOCUS.items():
            self.assertGreater(len(focus.strip()), 5, f"Empty focus for {cid}")


class TestPromptRendering(unittest.TestCase):
    def test_prompt_contains_clause_id(self):
        prompt = critic.CRITIC_PROMPT_TEMPLATE.format(
            clause_id="5.2",
            clause_name="Information Security Policy",
            rag_context="RAG content here",
            clause_focus=critic.CLAUSE_FOCUS["5.2"],
            org_name="Test Corp",
            org_industry="Testing",
            org_size="10 employees",
            org_scope="Test scope",
            legal_basis="GDPR",
            document="Draft document text",
            revision_instructions=critic.REVISION_INSTRUCTIONS_TEMPLATE,
        )
        self.assertIn("5.2", prompt)
        self.assertIn("Test Corp", prompt)
        self.assertIn("RAG content here", prompt)
        self.assertIn("Draft document text", prompt)

    def test_prompt_contains_five_checks(self):
        prompt = critic.CRITIC_PROMPT_TEMPLATE.format(
            clause_id="6.1.2",
            clause_name="Risk Assessment",
            rag_context="RAG",
            clause_focus=critic.CLAUSE_FOCUS["6.1.2"],
            org_name="Test Corp",
            org_industry="IT",
            org_size="50 employees",
            org_scope="scope",
            legal_basis="GDPR",
            document="doc",
            revision_instructions=critic.REVISION_INSTRUCTIONS_TEMPLATE,
        )
        for check in ["ISO MAPPING", "COMPLETENESS", "ORG SPECIFICITY", "INTERNAL CONSISTENCY", "AUDIT READINESS"]:
            self.assertIn(check, prompt)


class TestRunCriticCacheHit(unittest.TestCase):
    def test_cached_critic_skips_ollama(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir)
            clause_id = "4.3"

            (outputs_dir / f"{clause_id}.md").write_text("Draft document content", encoding="utf-8")
            (outputs_dir / f"{clause_id}.critic.md").write_text(PASS_OUTPUT, encoding="utf-8")

            cfg = {
                "llm": {"base_url": "http://localhost:11434"},
                "rag": {"chroma_db_path": "rag/chroma_db", "collection_name": "iso27001"},
                "paths": {"outputs": str(outputs_dir)},
                "critic": {"model": "qwen2.5:1.5b", "temperature": 0.1},
            }

            with patch("critic.call_ollama") as mock_ollama:
                assessment, text = critic.run_critic(clause_id, cfg, SAMPLE_ORG, force=False)
                mock_ollama.assert_not_called()
                self.assertEqual(assessment, "PASS")

    def test_force_bypasses_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir)
            clause_id = "4.3"

            (outputs_dir / f"{clause_id}.md").write_text("Draft document content", encoding="utf-8")
            (outputs_dir / f"{clause_id}.critic.md").write_text(PASS_OUTPUT, encoding="utf-8")

            cfg = {
                "llm": {"base_url": "http://localhost:11434"},
                "rag": {"chroma_db_path": "rag/chroma_db", "collection_name": "iso27001"},
                "paths": {"outputs": str(outputs_dir)},
                "critic": {"model": "qwen2.5:1.5b", "temperature": 0.1},
            }

            new_review = CONDITIONAL_OUTPUT
            with patch("critic.call_ollama", return_value=new_review) as mock_ollama:
                with patch("critic.get_rag_context_for_critic", return_value="RAG context"):
                    assessment, text = critic.run_critic(clause_id, cfg, SAMPLE_ORG, force=True)
                    mock_ollama.assert_called_once()
                    self.assertEqual(assessment, "CONDITIONAL PASS")
                    self.assertEqual(
                        (outputs_dir / f"{clause_id}.critic.md").read_text(),
                        new_review,
                    )


class TestRunCriticNoDocument(unittest.TestCase):
    def test_missing_document_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = {
                "llm": {"base_url": "http://localhost:11434"},
                "rag": {"chroma_db_path": "rag/chroma_db", "collection_name": "iso27001"},
                "paths": {"outputs": str(tmpdir)},
                "critic": {"model": "qwen2.5:1.5b", "temperature": 0.1},
            }
            assessment, text = critic.run_critic("99.9", cfg, SAMPLE_ORG)
            self.assertIsNone(assessment)
            self.assertIsNone(text)


class TestOllamaConnectionError(unittest.TestCase):
    def test_connection_error_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            critic.call_ollama("http://localhost:9999", "model", "prompt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
