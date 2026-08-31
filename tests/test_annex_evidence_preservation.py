"""Test that Annex A evidence is preserved when saving unvisited controls."""
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAnnexEvidencePreservation(unittest.TestCase):
    """Regression test for issue: Annex A evidence silently wiped on save."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.evidence_file = self.tmpdir / "annex_a_evidence.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_control_absent_from_session_state_keeps_persisted_evidence(self):
        """When a control isn't visited (not in session_state), its evidence is retained."""
        # Create persisted evidence for two controls
        persisted_evidence = {
            "A.5.1": {
                "applicable": True,
                "status": "Implemented",
                "justification": "We have a robust access control policy",
                "evidence_refs": ["policy-doc-001.pdf", "audit-report-2024.pdf"],
            },
            "A.5.2": {
                "applicable": True,
                "status": "Partial",
                "justification": "",
                "evidence_refs": [],
            },
        }
        self.evidence_file.write_text(
            json.dumps(persisted_evidence), encoding="utf-8"
        )

        # Simulate session_state with only A.5.2 edited (A.5.1 not visited)
        mock_session_state = {
            "annex_A.5.2_applicable": True,
            "annex_A.5.2_status": "Implemented",
            "annex_A.5.2_justification": "Updated justification",
            "annex_A.5.2_evidence": "new-evidence-ref.pdf",
            # A.5.1 keys are NOT in session_state (control not visited)
        }

        # Mock dependencies
        with patch("ui.core.st") as mock_st, \
             patch("ui.core.ANNEX_A_EVIDENCE_FILE", self.evidence_file), \
             patch("ui.core.ANNEX_A_CONTROLS", {"A.5.1": {}, "A.5.2": {}}):

            mock_st.session_state = mock_session_state

            # Import after mocking
            from ui.core import _annex_collect_from_state

            result = _annex_collect_from_state()

        # A.5.1 should retain all its original evidence
        self.assertIn("A.5.1", result)
        self.assertEqual(result["A.5.1"]["status"], "Implemented")
        self.assertEqual(
            result["A.5.1"]["evidence_refs"],
            ["policy-doc-001.pdf", "audit-report-2024.pdf"],
        )

        # A.5.2 should have updated evidence
        self.assertIn("A.5.2", result)
        self.assertEqual(result["A.5.2"]["status"], "Implemented")
        self.assertEqual(result["A.5.2"]["justification"], "Updated justification")
        self.assertEqual(result["A.5.2"]["evidence_refs"], ["new-evidence-ref.pdf"])

    def test_newly_visited_control_uses_session_state_values(self):
        """When a control is visited, its session_state values override persisted defaults."""
        # Empty persisted file
        self.evidence_file.write_text("{}", encoding="utf-8")

        # Session state has a newly visited control
        mock_session_state = {
            "annex_A.6.1_applicable": True,
            "annex_A.6.1_status": "Implemented",
            "annex_A.6.1_justification": "New control entry",
            "annex_A.6.1_evidence": "evidence-file.pdf",
        }

        with patch("ui.core.st") as mock_st, \
             patch("ui.core.ANNEX_A_EVIDENCE_FILE", self.evidence_file), \
             patch("ui.core.ANNEX_A_CONTROLS", {"A.6.1": {}}):

            mock_st.session_state = mock_session_state

            from ui.core import _annex_collect_from_state

            result = _annex_collect_from_state()

        self.assertIn("A.6.1", result)
        self.assertEqual(result["A.6.1"]["status"], "Implemented")
        self.assertEqual(result["A.6.1"]["justification"], "New control entry")
        self.assertEqual(result["A.6.1"]["evidence_refs"], ["evidence-file.pdf"])


if __name__ == "__main__":
    unittest.main()
