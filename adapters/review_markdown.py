"""Render a typed ReviewVerdict back to the markdown shape critic.py used to hand-emit.

Keeps every existing markdown consumer (pipeline.py's extract_critic_findings(),
the Review tab's .critic.md viewer, .critic.attempt-N.md snapshots) working unchanged
while the underlying data becomes structurally guaranteed instead of prompt-hoped.
"""

from schemas.review import ReviewVerdict

_DIMENSION_ORDER = [
    "ISO Mapping",
    "Completeness",
    "Org Specificity",
    "Internal Consistency",
    "Audit Readiness",
]


def verdict_to_markdown(v: ReviewVerdict) -> str:
    by_dimension = {f.dimension: f for f in v.findings}
    rows = "\n".join(
        f"| {i} | {dim} | {by_dimension[dim].result} | {by_dimension[dim].detail} |"
        for i, dim in enumerate(_DIMENSION_ORDER, start=1)
    )

    revisions = (
        "None — document meets requirements."
        if not v.required_revisions
        else "\n".join(f"- {r}" for r in v.required_revisions)
    )

    return f"""## Critic Review — Clause {v.clause_id}: {v.clause_name}

**Overall Assessment:** {v.overall_assessment}
**Confidence:** {v.confidence}

### Findings Table
| # | Check | Result | Detail |
|---|-------|--------|--------|
{rows}

### Required Revisions
{revisions}

### Auditor Verdict
{v.auditor_verdict}
"""
