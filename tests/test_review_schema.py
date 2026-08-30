"""
Tests for schemas/review.py — ReviewVerdict / FindingRow structural guarantees.
No real LLM calls.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import ValidationError

from schemas.review import FindingRow, ReviewVerdict


def _finding(dimension, result="PASS", detail="ok"):
    return FindingRow(dimension=dimension, result=result, detail=detail)


FIVE_DIMENSIONS = [
    "ISO Mapping",
    "Completeness",
    "Org Specificity",
    "Internal Consistency",
    "Audit Readiness",
]


def _valid_verdict(**overrides):
    data = dict(
        clause_id="4.3",
        clause_name="Scope",
        overall_assessment="PASS",
        confidence="HIGH",
        findings=[_finding(d) for d in FIVE_DIMENSIONS],
        required_revisions=[],
        auditor_verdict="This document would pass a Stage 2 audit.",
    )
    data.update(overrides)
    return ReviewVerdict(**data)


class TestFindingRow(unittest.TestCase):
    def test_valid_result_literal_accepted(self):
        for result in ("PASS", "WARN", "FAIL"):
            row = _finding("ISO Mapping", result=result)
            self.assertEqual(row.result, result)

    def test_invalid_result_rejected(self):
        with self.assertRaises(ValidationError):
            FindingRow(dimension="ISO Mapping", result="MAYBE", detail="x")

    def test_invalid_dimension_rejected(self):
        with self.assertRaises(ValidationError):
            FindingRow(dimension="Not A Real Dimension", result="PASS", detail="x")


class TestReviewVerdict(unittest.TestCase):
    def test_valid_verdict_round_trips(self):
        v = _valid_verdict()
        self.assertEqual(v.overall_assessment, "PASS")
        self.assertEqual(len(v.findings), 5)

    def test_findings_must_be_exactly_five(self):
        with self.assertRaises(ValidationError):
            _valid_verdict(findings=[_finding(d) for d in FIVE_DIMENSIONS[:4]])

    def test_findings_reject_more_than_five(self):
        with self.assertRaises(ValidationError):
            _valid_verdict(findings=[_finding(d) for d in FIVE_DIMENSIONS] + [_finding(FIVE_DIMENSIONS[0])])

    def test_invalid_overall_assessment_rejected(self):
        with self.assertRaises(ValidationError):
            _valid_verdict(overall_assessment="MAYBE")

    def test_invalid_confidence_rejected(self):
        with self.assertRaises(ValidationError):
            _valid_verdict(confidence="SUPER_HIGH")

    def test_required_revisions_defaults_empty(self):
        v = _valid_verdict()
        self.assertEqual(v.required_revisions, [])

    def test_findings_reject_duplicate_dimension(self):
        """Duplicate dimension should raise ValidationError."""
        with self.assertRaises(ValidationError):
            _valid_verdict(
                findings=[
                    _finding("ISO Mapping"),
                    _finding("ISO Mapping"),  # duplicate
                    _finding("Completeness"),
                    _finding("Org Specificity"),
                    _finding("Internal Consistency"),
                    # "Audit Readiness" is missing
                ]
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
