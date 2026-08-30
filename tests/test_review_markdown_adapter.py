"""
Tests for adapters/review_markdown.py — verdict_to_markdown() must stay byte-compatible
with the markdown shape critic.py used to hand-emit, since pipeline.py's
extract_critic_findings() still string-matches "### Findings Table" / "### Required Revisions"
and the Review tab still renders the .critic.md file as markdown.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.review_markdown import verdict_to_markdown
from schemas.review import FindingRow, ReviewVerdict

VERDICT = ReviewVerdict(
    clause_id="4.3",
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


class TestVerdictToMarkdown(unittest.TestCase):
    def setUp(self):
        self.md = verdict_to_markdown(VERDICT)

    def test_header_contains_clause_id_and_name(self):
        self.assertIn("## Critic Review — Clause 4.3: Scope", self.md)

    def test_overall_assessment_line(self):
        self.assertIn("**Overall Assessment:** CONDITIONAL PASS", self.md)

    def test_confidence_line(self):
        self.assertIn("**Confidence:** MEDIUM", self.md)

    def test_findings_table_heading_present(self):
        self.assertIn("### Findings Table", self.md)

    def test_findings_table_rows_present(self):
        self.assertIn("| 1 | ISO Mapping | PASS | All mandatory elements present |", self.md)
        self.assertIn("| 5 | Audit Readiness | WARN | Needs minor fixes |", self.md)

    def test_required_revisions_heading_and_items(self):
        self.assertIn("### Required Revisions", self.md)
        self.assertIn("Add exclusions justification.", self.md)
        self.assertIn("Clarify audit readiness gap.", self.md)

    def test_auditor_verdict_heading_and_text(self):
        self.assertIn("### Auditor Verdict", self.md)
        self.assertIn("This document is close but needs two fixes before Stage 2.", self.md)

    def test_pass_with_no_revisions_shows_none_message(self):
        v = ReviewVerdict(
            clause_id="4.3",
            clause_name="Scope",
            overall_assessment="PASS",
            confidence="HIGH",
            findings=[
                FindingRow(dimension=d, result="PASS", detail="ok")
                for d in ("ISO Mapping", "Completeness", "Org Specificity", "Internal Consistency", "Audit Readiness")
            ],
            required_revisions=[],
            auditor_verdict="Ready.",
        )
        md = verdict_to_markdown(v)
        self.assertIn("None — document meets requirements.", md)

    def test_extract_critic_findings_still_works_on_adapter_output(self):
        # pipeline.py's extract_critic_findings() string-matches these headings —
        # confirm the adapter's output still satisfies that contract.
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from pipeline import extract_critic_findings
        extracted = extract_critic_findings(self.md)
        self.assertIn("### Findings Table", extracted)
        self.assertIn("### Required Revisions", extracted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
