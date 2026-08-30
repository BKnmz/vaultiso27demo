"""Typed AI Reviewer output — replaces critic.py's markdown table + regex parsing.

Ollama's grammar-constrained decoding (format=json_schema, XGrammar) enforces these
Literal/list-length constraints at the token level, so the model cannot emit an
ambiguous verdict or echo a bracketed placeholder the way free-form markdown could.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Dimension = Literal[
    "ISO Mapping",
    "Completeness",
    "Org Specificity",
    "Internal Consistency",
    "Audit Readiness",
]

Result = Literal["PASS", "WARN", "FAIL"]
OverallAssessment = Literal["PASS", "CONDITIONAL PASS", "FAIL"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]


class FindingRow(BaseModel):
    dimension: Dimension
    result: Result
    detail: str


class ReviewVerdict(BaseModel):
    clause_id: str
    clause_name: str
    overall_assessment: OverallAssessment
    confidence: Confidence
    findings: list[FindingRow] = Field(min_length=5, max_length=5)
    required_revisions: list[str] = Field(default_factory=list)
    auditor_verdict: str

    @model_validator(mode="after")
    def validate_all_dimensions_present_once(self) -> "ReviewVerdict":
        """Ensure findings contain exactly one of each canonical dimension."""
        canonical_dimensions = {
            "ISO Mapping",
            "Completeness",
            "Org Specificity",
            "Internal Consistency",
            "Audit Readiness",
        }
        found_dimensions = {f.dimension for f in self.findings}

        if found_dimensions != canonical_dimensions:
            missing = canonical_dimensions - found_dimensions
            duplicated = []
            seen = set()
            for f in self.findings:
                if f.dimension in seen:
                    duplicated.append(f.dimension)
                seen.add(f.dimension)
            duplicated = list(set(duplicated))

            msg_parts = []
            if missing:
                msg_parts.append(f"missing: {', '.join(sorted(missing))}")
            if duplicated:
                msg_parts.append(f"duplicated: {', '.join(sorted(duplicated))}")

            raise ValueError(
                f"findings must contain exactly one of each dimension ({', '.join(msg_parts)})"
            )

        return self
