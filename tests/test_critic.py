"""
Tests for critic.py — assessment parsing, CLAUSE_FOCUS completeness, prompt rendering, mock Ollama.
No real LLM calls.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import critic

from schemas.review import FindingRow, ReviewVerdict


SAMPLE_ORG = {
    "name": "Test Corp",
    "industry": "Testing",
    "size": "10 employees",
    "scope": "Test scope",
    "legal_basis": ["GDPR"],
}

FIVE_DIMENSIONS = [
    "ISO Mapping",
    "Completeness",
    "Org Specificity",
    "Internal Consistency",
    "Audit Readiness",
]


def _verdict(overall_assessment="PASS", clause_id="4.3", clause_name="Scope"):
    return ReviewVerdict(
        clause_id=clause_id,
        clause_name=clause_name,
        overall_assessment=overall_assessment,
        confidence="HIGH",
        findings=[FindingRow(dimension=d, result="PASS", detail="ok") for d in FIVE_DIMENSIONS],
        required_revisions=[],
        auditor_verdict="Ready.",
    )

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

    def test_placeholder_echo_is_unknown_not_fail(self):
        # Model copied the bracketed template verbatim instead of deciding.
        # This must surface as UNKNOWN, not a silent FAIL on the example text.
        text = "**Overall Assessment:** [PASS / CONDITIONAL PASS / FAIL]"
        self.assertEqual(critic.parse_overall_assessment(text), "UNKNOWN")

    def test_conditional_checked_before_fail(self):
        # A line mentioning both words must resolve to CONDITIONAL PASS,
        # not FAIL (FAIL-first ordering was the bug).
        text = "**Overall Assessment:** CONDITIONAL PASS (would otherwise FAIL without fixes)"
        self.assertEqual(critic.parse_overall_assessment(text), "CONDITIONAL PASS")


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
        # This is the one test that lets run_sync() execute for real (a genuine
        # connection attempt to a closed port, no Agent/OpenAIProvider mocks) — it
        # trips pydantic_graph's internal asyncio.get_event_loop() DeprecationWarning
        # on Python 3.12 when no event loop yet exists in this thread. That warning
        # is pydantic-ai library-internal noise, unrelated to the behavior under
        # test, so it's suppressed here to keep test output pristine.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with self.assertRaises(SystemExit):
                critic.run_reviewer_agent("http://localhost:9999", "model", "prompt")


class TestReviewerAgentNoCloudApi(unittest.TestCase):
    def test_base_url_never_points_at_a_real_cloud_endpoint(self):
        # Auditable guard: the reviewer agent must only ever be constructed against
        # the locally-configured Ollama base_url, never a literal OpenAI/Anthropic host.
        from pydantic_ai.providers.openai import OpenAIProvider as RealOpenAIProvider

        captured = {}

        def _spy_provider(*, base_url, api_key=None):
            captured["base_url"] = base_url
            captured["api_key"] = api_key
            return RealOpenAIProvider(base_url=base_url, api_key=api_key)

        with patch("critic.OpenAIProvider", _spy_provider), \
             patch("critic.Agent") as mock_agent_cls:
            mock_agent_cls.return_value.run_sync.return_value.output = _verdict("PASS")
            critic.run_reviewer_agent("http://localhost:11434", "qwen2.5:1.5b", "prompt")

        self.assertIn("localhost:11434", captured["base_url"])
        self.assertNotIn("api.openai.com", captured["base_url"])

    def test_api_key_is_never_read_from_environment(self):
        # Even if a real OPENAI_API_KEY happens to be set on the dev machine (common,
        # for unrelated projects), the reviewer agent must never inherit it — api_key
        # is always the hardcoded dummy "ollama", independent of environment state.
        import os

        captured = {}

        def _spy_provider(*, base_url, api_key=None):
            captured["api_key"] = api_key
            return MagicMock()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-real-looking-key-do-not-use"}), \
             patch("critic.OpenAIProvider", _spy_provider), \
             patch("critic.Agent") as mock_agent_cls:
            mock_agent_cls.return_value.run_sync.return_value.output = _verdict("PASS")
            critic.run_reviewer_agent("http://localhost:11434", "qwen2.5:1.5b", "prompt")

        self.assertEqual(captured["api_key"], "ollama")

    def test_empty_base_url_raises_before_any_network_call(self):
        with patch("critic.Agent") as mock_agent_cls, patch("critic.OpenAIProvider") as mock_provider:
            with self.assertRaises(ValueError):
                critic.run_reviewer_agent("", "qwen2.5:1.5b", "prompt")
        mock_provider.assert_not_called()
        mock_agent_cls.assert_not_called()


class TestReviewerAgentUsesNativeOutput(unittest.TestCase):
    def test_agent_constructed_with_native_output(self):
        # A bare `output_type=ReviewVerdict` defaults pydantic-ai to tool-calling for
        # structured output, which small local models (e.g. qwen2.5:1.5b) unreliably
        # invoke — confirmed empirically: it exhausted retries against real Ollama.
        # NativeOutput forces Ollama's grammar-constrained json_schema mode instead,
        # which is enforced at the token level regardless of model size.
        from pydantic_ai import NativeOutput

        with patch("critic.OpenAIProvider"), patch("critic.Agent") as mock_agent_cls:
            mock_agent_cls.return_value.run_sync.return_value.output = _verdict("PASS")
            critic.run_reviewer_agent("http://localhost:11434", "qwen2.5:1.5b", "prompt")

        _, kwargs = mock_agent_cls.call_args
        self.assertIsInstance(kwargs.get("output_type"), NativeOutput)


class TestReviewerAgentModelSwapRetry(unittest.TestCase):
    def test_500_on_first_attempt_retries_once_then_succeeds(self):
        from pydantic_ai.exceptions import ModelHTTPError

        good_result = MagicMock()
        good_result.output = _verdict("PASS")

        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = [
            ModelHTTPError(status_code=500, model_name="qwen2.5:1.5b"),
            good_result,
        ]

        with patch("critic.Agent", return_value=mock_agent), \
             patch("critic.OpenAIProvider"), \
             patch("critic.time.sleep") as mock_sleep:
            verdict = critic.run_reviewer_agent("http://localhost:11434", "qwen2.5:1.5b", "prompt")

        self.assertEqual(verdict.overall_assessment, "PASS")
        self.assertEqual(mock_agent.run_sync.call_count, 2)
        mock_sleep.assert_called_once_with(12)

    def test_500_on_second_attempt_raises_runtime_error(self):
        from pydantic_ai.exceptions import ModelHTTPError

        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = ModelHTTPError(status_code=500, model_name="qwen2.5:1.5b")

        with patch("critic.Agent", return_value=mock_agent), \
             patch("critic.OpenAIProvider"), \
             patch("critic.time.sleep"):
            with self.assertRaises(RuntimeError):
                critic.run_reviewer_agent("http://localhost:11434", "qwen2.5:1.5b", "prompt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
