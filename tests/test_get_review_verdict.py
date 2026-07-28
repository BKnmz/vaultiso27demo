"""
Tests for ui/core.py:get_review_verdict() — direct file-reading behavior for
typed ReviewVerdict JSON sidecars alongside .critic.md files.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "ui"))

import core  # noqa: E402
from schemas.review import FindingRow, ReviewVerdict  # noqa: E402


def _make_valid_verdict(clause_id="4.3") -> ReviewVerdict:
    """Create a valid ReviewVerdict for testing."""
    return ReviewVerdict(
        clause_id=clause_id,
        clause_name="Scope",
        overall_assessment="CONDITIONAL PASS",
        confidence="MEDIUM",
        findings=[
            FindingRow(dimension="ISO Mapping", result="PASS", detail="All mandatory elements present"),
            FindingRow(dimension="Completeness", result="WARN", detail="Missing exclusions justification"),
            FindingRow(dimension="Org Specificity", result="PASS", detail="Specific to org"),
            FindingRow(dimension="Internal Consistency", result="PASS", detail="No contradictions"),
            FindingRow(dimension="Audit Readiness", result="WARN", detail="Needs minor fixes"),
        ],
        required_revisions=["Add exclusions justification.", "Clarify audit readiness gap."],
        auditor_verdict="This document is close but needs two fixes before Stage 2.",
    )


class TestGetReviewVerdictFileReading(unittest.TestCase):
    """Test get_review_verdict() with real file I/O using tempfile."""

    def test_returns_none_when_sidecar_missing(self):
        """No .critic.json file exists → returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(core, "OUTPUTS_DIR", Path(tmpdir)):
                result = core.get_review_verdict("4.3")
                self.assertIsNone(result)

    def test_returns_none_when_sidecar_corrupt(self):
        """Write invalid JSON to .critic.json → returns None (no exception raised)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Write corrupt JSON
            (tmpdir_path / "4.3.critic.json").write_text("{not valid json")

            with mock.patch.object(core, "OUTPUTS_DIR", tmpdir_path):
                result = core.get_review_verdict("4.3")
                self.assertIsNone(result)

    def test_returns_valid_verdict_when_sidecar_present(self):
        """Write a real ReviewVerdict JSON to .critic.json → returns matching ReviewVerdict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create and serialize a valid ReviewVerdict
            verdict = _make_valid_verdict("4.3")
            json_text = verdict.model_dump_json()
            (tmpdir_path / "4.3.critic.json").write_text(json_text)

            with mock.patch.object(core, "OUTPUTS_DIR", tmpdir_path):
                result = core.get_review_verdict("4.3")

                # Verify result is a ReviewVerdict with matching fields
                self.assertIsInstance(result, ReviewVerdict)
                self.assertEqual(result.clause_id, "4.3")
                self.assertEqual(result.clause_name, "Scope")
                self.assertEqual(result.overall_assessment, "CONDITIONAL PASS")
                self.assertEqual(result.confidence, "MEDIUM")
                self.assertEqual(len(result.findings), 5)
                self.assertEqual(result.findings[0].dimension, "ISO Mapping")
                self.assertEqual(result.auditor_verdict, "This document is close but needs two fixes before Stage 2.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
