"""
Tests for ui/core.py's org/personnel extraction — the pure agent-call helpers
(_extract_org_agent_call / _extract_personnel_agent_call) and the thin
Streamlit-wrapped public functions (extract_org_with_llm / extract_personnel_with_llm).
No real LLM calls; the pydantic-ai Agent is mocked at the boundary.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "ui"))

import core  # noqa: E402
from schemas.org_profile import OrgProfile, PersonnelEntry  # noqa: E402

CFG = {"llm": {"base_url": "http://localhost:11434", "model": "phi4-mini:3.8b-q4_K_M"}}


class TestExtractOrgAgentCall(unittest.TestCase):
    def test_returns_org_profile_from_agent_output(self):
        canned = OrgProfile(name="Acme Corp", industry="Manufacturing")
        with patch("core.Agent") as mock_agent_cls, patch("core.OpenAIProvider"):
            mock_agent_cls.return_value.run_sync.return_value.output = canned
            result = core._extract_org_agent_call("some document text", CFG)
        self.assertEqual(result, canned)


class TestExtractOrgWithLlm(unittest.TestCase):
    def test_success_returns_plain_dict_not_pydantic_model(self):
        canned = OrgProfile(name="Acme Corp", locations=["Berlin"])
        with patch("core.requests.get"), \
             patch("core._extract_org_agent_call", return_value=canned):
            result = core.extract_org_with_llm("doc text", CFG)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["name"], "Acme Corp")
        self.assertEqual(result["locations"], ["Berlin"])

    def test_unreachable_engine_shows_error_and_returns_none(self):
        with patch("core.requests.get", side_effect=Exception("refused")), \
             patch("core.st.error") as mock_error:
            result = core.extract_org_with_llm("doc text", CFG)
        self.assertIsNone(result)
        mock_error.assert_called_once()

    def test_agent_failure_shows_error_and_returns_none(self):
        with patch("core.requests.get"), \
             patch("core._extract_org_agent_call", side_effect=RuntimeError("boom")), \
             patch("core.st.error") as mock_error:
            result = core.extract_org_with_llm("doc text", CFG)
        self.assertIsNone(result)
        mock_error.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
