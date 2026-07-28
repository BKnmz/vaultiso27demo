"""
Tests for ui/_pages/review.py:_render_reviewer_findings() — must render a typed
ReviewVerdict directly (post pydantic-ai migration) and still fall back to
regex-parsing legacy markdown for .critic.md files generated before the migration
(no .critic.json sidecar, so no ReviewVerdict available).
"""

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "ui"))
sys.path.insert(0, str(_ROOT / "ui" / "_pages"))

import review  # noqa: E402
from schemas.review import FindingRow, ReviewVerdict  # noqa: E402

FIVE_DIMENSIONS = [
    "ISO Mapping",
    "Completeness",
    "Org Specificity",
    "Internal Consistency",
    "Audit Readiness",
]

LEGACY_MARKDOWN = """## Critic Review — Clause 4.3: Scope

**Overall Assessment:** CONDITIONAL PASS
**Confidence:** MEDIUM

### Findings Table
| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | ISO Mapping | PASS | All mandatory elements present |
| 2 | Completeness | WARN | Missing exclusions justification |
| 3 | Org Specificity | PASS | Specific to org |
| 4 | Internal Consistency | PASS | No contradictions |
| 5 | Audit Readiness | WARN | Needs minor fixes |

### Required Revisions
- Add exclusions justification.
- Clarify audit readiness gap.

### Auditor Verdict
This document is close but needs two fixes before Stage 2.
"""


def _verdict(overall_assessment="CONDITIONAL PASS"):
    return ReviewVerdict(
        clause_id="4.3",
        clause_name="Scope",
        overall_assessment=overall_assessment,
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


class TestRenderFromTypedVerdict(unittest.TestCase):
    def test_renders_all_five_dimensions(self):
        html = review._render_reviewer_findings(_verdict(), rev_text="")
        for dim in FIVE_DIMENSIONS:
            self.assertIn(dim, html)

    def test_renders_finding_detail_text(self):
        html = review._render_reviewer_findings(_verdict(), rev_text="")
        self.assertIn("Missing exclusions justification", html)

    def test_conditional_pass_shows_fix_callout_with_revisions(self):
        html = review._render_reviewer_findings(_verdict("CONDITIONAL PASS"), rev_text="")
        self.assertIn("What needs fixing", html)
        self.assertIn("Add exclusions justification.", html)

    def test_pass_with_no_revisions_omits_fix_callout(self):
        v = _verdict("PASS")
        v = v.model_copy(update={"required_revisions": []})
        html = review._render_reviewer_findings(v, rev_text="")
        self.assertNotIn("What needs fixing", html)


class TestRenderFallsBackToLegacyMarkdown(unittest.TestCase):
    def test_no_verdict_falls_back_to_markdown_parse(self):
        html = review._render_reviewer_findings(None, rev_text=LEGACY_MARKDOWN)
        for dim in FIVE_DIMENSIONS:
            self.assertIn(dim, html)
        self.assertIn("What needs fixing", html)
        self.assertIn("Add exclusions justification.", html)

    def test_no_verdict_and_no_text_shows_nothing_crashy(self):
        html = review._render_reviewer_findings(None, rev_text="")
        self.assertIsInstance(html, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
