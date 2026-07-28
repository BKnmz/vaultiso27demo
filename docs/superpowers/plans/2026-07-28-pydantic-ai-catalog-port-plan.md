# Port pydantic-ai Migration + Model Catalog to Demo Repo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the pydantic-ai typed-agent migration (AI Reviewer + org/personnel extraction) and the model-catalog JSON split from the main tool (`isms-automation`) into the demo repo (`vaultiso-demo`), matching the main tool's proven implementation exactly, plus two demo-specific offline-invariant hardenings a security review flagged as missing even from the main tool.

**Architecture:** Three independent phases (Reviewer, org extraction, model catalog), each executed as a small devsecops loop: implement with TDD → security/code-review checkpoint → full pytest run → commit, before starting the next phase. Every phase's target code already exists, tested and running, in the main tool — this plan ports it verbatim where the two repos match, and adapts it only where the spec's fact-check found real divergence (`setup_config.py`'s from-scratch `TIERS`→catalog split).

**Tech Stack:** Python, pydantic / pydantic-ai (`NativeOutput` structured generation against Ollama's OpenAI-compatible endpoint), pytest/unittest, Streamlit.

**Spec:** `docs/superpowers/specs/2026-07-27-pydantic-ai-catalog-port-design.md`

## Global Constraints

- **Offline/no-cloud invariant** — every pydantic-ai agent must construct its provider as `OpenAIProvider(base_url=f"{base_url}/v1", api_key="ollama")`. `api_key` is ALWAYS the literal string `"ollama"` — never read from `OPENAI_API_KEY` or any environment variable. If `base_url` is falsy, raise immediately before constructing the provider — never let the OpenAI SDK fall through to `https://api.openai.com`.
- **`pydantic-ai-slim[openai]==2.9.0`** — exact pin, `slim` + `openai` extra only. Never add `anthropic` or `google` provider extras.
- **`NativeOutput(SchemaClass)`**, never bare `output_type=SchemaClass` — bare mode defaults to tool-calling, which `qwen2.5:1.5b` exhausts retries on; `NativeOutput` forces Ollama's grammar-constrained `json_schema` mode, enforced at the token level regardless of model size.
- **Ollama 0.5.0+ floor** — the version that introduced grammar-constrained structured output. Advisory-only warning, must fail open (never block startup) on an unparseable version string.
- **Baseline:** `python -m pytest tests/ -q` currently passes 105/105 in `vaultiso-demo`. No task in this plan may leave that number lower than where it started.
- **No new runtime dependency beyond `pydantic-ai-slim[openai]`** — `chromadb`, `sentence-transformers`, `torch` etc. stay as pinned today.

---

## File Structure

**New files:**
- `schemas/__init__.py` — empty package marker
- `schemas/review.py` — `ReviewVerdict` / `FindingRow` (typed AI Reviewer output)
- `schemas/org_profile.py` — `OrgProfile` / `PersonnelEntry` / `AssetEntry` / `StakeholderEntry`
- `adapters/__init__.py` — empty package marker
- `adapters/review_markdown.py` — `verdict_to_markdown()`
- `models_catalog.json` — per-tier model identity, source of truth for `setup_config.py`
- `tests/test_review_schema.py`, `tests/test_review_markdown_adapter.py`, `tests/test_review_findings_render.py`, `tests/test_launch_ollama_version.py`, `tests/test_org_profile_schema.py`, `tests/test_org_extraction.py`

**Modified files:**
- `critic.py` — `run_reviewer_agent()` replaces `call_ollama()`; `.critic.json` sidecar; cache-hit prefers JSON
- `ui/core.py` — `get_review_verdict()`; `extract_org_with_llm`/`extract_personnel_with_llm` split into pure agent-call + thin wrapper
- `ui/_pages/review.py` — `_render_reviewer_findings()` takes typed verdict first, falls back to legacy regex parse
- `launch.py` — non-blocking Ollama version warning
- `setup_config.py` — `TIERS` split into `_TIER_TUNING` (Python) + `models_catalog.json` (model identity), merged at import
- `requirements.txt` — add `pydantic-ai-slim[openai]==2.9.0`
- `.gitignore` — add `models_catalog.online_cache.json`
- `tests/test_critic.py`, `tests/test_setup_config.py` — extended in place with new test classes

---

## PHASE 1 — Reviewer → pydantic-ai

### Task 1: Typed ReviewVerdict schema + markdown adapter

**Model:** haiku (verbatim port of a proven, already-tested main-tool file — no design judgment needed)

**Files:**
- Create: `schemas/__init__.py`
- Create: `schemas/review.py`
- Create: `adapters/__init__.py`
- Create: `adapters/review_markdown.py`
- Test: `tests/test_review_schema.py`
- Test: `tests/test_review_markdown_adapter.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `schemas.review.ReviewVerdict(clause_id, clause_name, overall_assessment, confidence, findings, required_revisions, auditor_verdict)`, `schemas.review.FindingRow(dimension, result, detail)`, `adapters.review_markdown.verdict_to_markdown(v: ReviewVerdict) -> str`. Task 2/3 consume these directly.

- [ ] **Step 1: Add the dependency pin**

Edit `requirements.txt`, append as the last line:

```
pydantic-ai-slim[openai]==2.9.0
```

- [ ] **Step 2: Install it**

Run: `pip install pydantic-ai-slim[openai]==2.9.0` (inside the project's `.venv`)
Expected: install succeeds, no dependency conflicts with the existing pin set.

- [ ] **Step 3: Create the schema package**

Create `schemas/__init__.py` (empty file).

Create `schemas/review.py`:

```python
"""Typed AI Reviewer output — replaces critic.py's markdown table + regex parsing.

Ollama's grammar-constrained decoding (format=json_schema, XGrammar) enforces these
Literal/list-length constraints at the token level, so the model cannot emit an
ambiguous verdict or echo a bracketed placeholder the way free-form markdown could.
"""

from typing import Literal

from pydantic import BaseModel, Field

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
```

- [ ] **Step 4: Write the failing schema tests**

Create `tests/test_review_schema.py`:

```python
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

Run: `python -m pytest tests/test_review_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'schemas'` (schemas/review.py not yet created — if Step 3 was already done, this should instead PASS; run this step before Step 3 if following strict TDD order).

- [ ] **Step 5: Confirm schema tests pass**

Run: `python -m pytest tests/test_review_schema.py -v`
Expected: `9 passed`

- [ ] **Step 6: Create the markdown adapter**

Create `adapters/__init__.py` (empty file).

Create `adapters/review_markdown.py`:

```python
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
```

- [ ] **Step 7: Write the adapter tests**

Create `tests/test_review_markdown_adapter.py`:

```python
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
```

- [ ] **Step 8: Run and confirm all Task 1 tests pass**

Run: `python -m pytest tests/test_review_schema.py tests/test_review_markdown_adapter.py -v`
Expected: `18 passed`

- [ ] **Step 9: Commit**

```bash
git add schemas/ adapters/ requirements.txt tests/test_review_schema.py tests/test_review_markdown_adapter.py
git commit -m "feat: add typed ReviewVerdict schema + markdown adapter"
```

---

### Task 2: Hardened reviewer agent constructor

**Model:** sonnet (security-critical: this is the function that owns the offline invariant)

**Files:**
- Modify: `critic.py` (imports at top; add `run_reviewer_agent()` before `run_critic()`)
- Test: `tests/test_critic.py` (new test classes appended)

**Interfaces:**
- Consumes: `schemas.review.ReviewVerdict` (Task 1), `adapters.review_markdown.verdict_to_markdown` (Task 1, used by Task 3)
- Produces: `critic.run_reviewer_agent(base_url, model, prompt, temperature=0.1, timeout=600) -> ReviewVerdict`. Task 3 calls this directly.

- [ ] **Step 1: Write the failing tests first**

Open `tests/test_critic.py`. Add these imports at the top (after the existing `from unittest.mock import MagicMock, patch` line):

```python
import json

from schemas.review import FindingRow, ReviewVerdict
```

Add this helper right after the imports, before `SAMPLE_ORG`:

```python
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
```

Add these new test classes at the end of the file, before the `if __name__ == "__main__":` block:

```python
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
```

Also replace the existing `TestOllamaConnectionError` class (it currently calls `critic.call_ollama`, which this task removes):

```python
class TestOllamaConnectionError(unittest.TestCase):
    def test_connection_error_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            critic.run_reviewer_agent("http://localhost:9999", "model", "prompt")
```

Run: `python -m pytest tests/test_critic.py -v`
Expected: FAIL — `AttributeError: module 'critic' has no attribute 'run_reviewer_agent'` (and `TestOllamaConnectionError` fails the same way since `call_ollama` is being replaced conceptually but still exists until Step 2 — this is expected red state).

- [ ] **Step 2: Add the pydantic-ai imports to critic.py**

Modify `critic.py` — after the existing `import requests` / `import yaml` block (around line 22-23), add:

```python
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from adapters.review_markdown import verdict_to_markdown
from schemas.review import ReviewVerdict
```

Also add `import time` next to the existing `import argparse` / `import json` / `import logging` / `import os` / `import sys` block if not already present (it is not — `critic.py` currently has no `import time`).

- [ ] **Step 3: Implement `run_reviewer_agent()`**

Add this function to `critic.py` immediately after `load_org()` and before `get_rag_context_for_critic()`:

```python
def run_reviewer_agent(base_url, model, prompt, temperature=0.1, timeout=600):
    """
    Call the AI Reviewer via pydantic-ai, pointed at local Ollama's OpenAI-compatible
    endpoint (never a real cloud API — base_url always resolves to config's llm.base_url).

    Uses NativeOutput to force Ollama's grammar-constrained decoding (format=json_schema)
    rather than pydantic-ai's default tool-calling structured-output mode — confirmed
    empirically that qwen2.5:1.5b exhausts its output retries under tool-calling mode but
    succeeds first-try under NativeOutput, since the schema constraint is enforced at the
    token level regardless of the model's tool-calling reliability.

    api_key is always the hardcoded literal "ollama" — never read from OPENAI_API_KEY or
    any environment variable, so a real key set on the dev machine for an unrelated project
    can never combine with a misconfigured base_url to send a real, billed cloud request.

    Returns a ReviewVerdict. Raises ValueError if base_url is empty (fail loud rather than
    let the OpenAI SDK silently fall back to https://api.openai.com). Raises SystemExit on
    connection failure, RuntimeError on a persistent server error.
    """
    if not base_url:
        raise ValueError(
            "run_reviewer_agent: base_url is empty — refusing to let the OpenAI SDK "
            "fall back to its default (https://api.openai.com)."
        )
    provider = OpenAIProvider(base_url=f"{base_url}/v1", api_key="ollama")
    pyd_model = OpenAIChatModel(
        model,
        provider=provider,
        settings=ModelSettings(temperature=temperature, timeout=timeout),
    )
    agent = Agent(pyd_model, output_type=NativeOutput(ReviewVerdict))

    for attempt in range(1, 3):
        try:
            result = agent.run_sync(prompt)
            return result.output
        except ModelHTTPError as e:
            if attempt == 1 and e.status_code == 500:
                # Ollama 500 = model swap not yet complete; wait and retry once
                log.warning("[CRITIC] Ollama 500 on attempt %d — waiting 12s for model swap, retrying...", attempt)
                time.sleep(12)
                continue
            raise RuntimeError(f"Ollama server error: {e}")
        except ModelAPIError as e:
            raise SystemExit(
                f"\nERROR: Cannot connect to Ollama at {base_url}\n"
                "Make sure Ollama is running: 'ollama serve'"
            ) from e
    raise RuntimeError("Ollama failed after 2 attempts.")
```

Leave `call_ollama()` and `parse_overall_assessment()` in place for now — Task 3 removes `call_ollama()`'s usage from `run_critic()` and repurposes `parse_overall_assessment()` as the legacy-cache fallback.

- [ ] **Step 4: Run tests, confirm the new classes pass**

Run: `python -m pytest tests/test_critic.py -v`
Expected: all `TestReviewerAgent*` and `TestOllamaConnectionError` classes pass. (`TestRunCriticCacheHit`/`TestRunCriticNoDocument` still reference `call_ollama` and will still pass unchanged at this point — Task 3 updates them.)

- [ ] **Step 5: Commit**

```bash
git add critic.py tests/test_critic.py
git commit -m "feat: add hardened pydantic-ai reviewer agent constructor"
```

---

### Task 3: Wire `run_critic()` to the typed agent + JSON sidecar

**Model:** sonnet (changes cache-hit behavior and on-disk file contract — needs care)

**Files:**
- Modify: `critic.py` (`run_critic()` function body)
- Modify: `tests/test_critic.py` (`TestRunCriticCacheHit` gains a legacy-fallback test; `TestRunCriticCacheHit.test_force_bypasses_cache` updated)

**Interfaces:**
- Consumes: `critic.run_reviewer_agent()` (Task 2), `adapters.review_markdown.verdict_to_markdown()` (Task 1)
- Produces: `critic.run_critic(clause_id, cfg, org, force=False) -> (assessment: str, markdown_text: str)`, plus a new `outputs/<clause_id>.critic.json` sidecar file. Task 4 (`ui/core.py:get_review_verdict`) reads this sidecar.

- [ ] **Step 1: Update the cache-hit test and add the legacy-fallback test**

In `tests/test_critic.py`, replace the entire `TestRunCriticCacheHit` class with:

```python
class TestRunCriticCacheHit(unittest.TestCase):
    def test_cached_critic_skips_ollama(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir)
            clause_id = "4.3"

            (outputs_dir / f"{clause_id}.md").write_text("Draft document content", encoding="utf-8")
            (outputs_dir / f"{clause_id}.critic.md").write_text(PASS_OUTPUT, encoding="utf-8")
            (outputs_dir / f"{clause_id}.critic.json").write_text(
                _verdict("PASS").model_dump_json(), encoding="utf-8"
            )

            cfg = {
                "llm": {"base_url": "http://localhost:11434"},
                "rag": {"chroma_db_path": "rag/chroma_db", "collection_name": "iso27001"},
                "paths": {"outputs": str(outputs_dir)},
                "critic": {"model": "qwen2.5:1.5b", "temperature": 0.1},
            }

            with patch("critic.run_reviewer_agent") as mock_agent:
                assessment, text = critic.run_critic(clause_id, cfg, SAMPLE_ORG, force=False)
                mock_agent.assert_not_called()
                self.assertEqual(assessment, "PASS")

    def test_cached_critic_falls_back_to_markdown_parse_without_json_sidecar(self):
        # Legacy cache from before the pydantic-ai migration — no .critic.json sidecar yet.
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

            with patch("critic.run_reviewer_agent") as mock_agent:
                assessment, text = critic.run_critic(clause_id, cfg, SAMPLE_ORG, force=False)
                mock_agent.assert_not_called()
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

            new_verdict = _verdict("CONDITIONAL PASS")
            with patch("critic.run_reviewer_agent", return_value=new_verdict) as mock_agent:
                with patch("critic.get_rag_context_for_critic", return_value="RAG context"):
                    assessment, text = critic.run_critic(clause_id, cfg, SAMPLE_ORG, force=True)
                    mock_agent.assert_called_once()
                    self.assertEqual(assessment, "CONDITIONAL PASS")
                    self.assertIn("CONDITIONAL PASS", (outputs_dir / f"{clause_id}.critic.md").read_text())
                    saved_json = json.loads((outputs_dir / f"{clause_id}.critic.json").read_text())
                    self.assertEqual(saved_json["overall_assessment"], "CONDITIONAL PASS")
```

Run: `python -m pytest tests/test_critic.py::TestRunCriticCacheHit -v`
Expected: FAIL — `run_critic` still uses `call_ollama` and never writes `.critic.json`.

- [ ] **Step 2: Rewrite `run_critic()`**

In `critic.py`, replace the entire `run_critic()` function body with:

```python
def run_critic(clause_id, cfg, org, force=False):
    """
    Run adversarial critic on a generated clause document.
    Saves result to outputs/<clause_id>.critic.md and outputs/<clause_id>.critic.json
    Returns (assessment, critic_text) or (None, None) if skipped.
    """
    outputs_dir = Path(cfg["paths"]["outputs"])
    doc_file = outputs_dir / f"{clause_id}.md"
    critic_file = outputs_dir / f"{clause_id}.critic.md"
    critic_json_file = outputs_dir / f"{clause_id}.critic.json"

    if not doc_file.exists():
        log.warning("[SKIP] No generated document found for clause %s", clause_id)
        return None, None

    if not force and critic_file.exists():
        log.info("[CACHED] Critic review already exists for %s", clause_id)
        cached_md = critic_file.read_text(encoding="utf-8")
        if critic_json_file.exists():
            try:
                cached_verdict = ReviewVerdict.model_validate_json(
                    critic_json_file.read_text(encoding="utf-8")
                )
                return cached_verdict.overall_assessment, cached_md
            except Exception:
                pass  # fall through to legacy markdown parse
        return parse_overall_assessment(cached_md), cached_md

    document = doc_file.read_text(encoding="utf-8", errors="replace")
    clause_name = CLAUSE_NAMES.get(clause_id, clause_id)
    focus = CLAUSE_FOCUS.get(clause_id, "general ISO 27001 conformance")
    rag_context = get_rag_context_for_critic(clause_id, cfg)

    prompt = CRITIC_PROMPT_TEMPLATE.format(
        clause_id=clause_id,
        clause_name=clause_name,
        rag_context=rag_context,
        clause_focus=focus,
        org_name=org.get("name", ""),
        org_industry=org.get("industry", ""),
        org_size=org.get("size", ""),
        org_scope=org.get("scope", ""),
        legal_basis=", ".join(org.get("legal_basis", [])),
        document=document[:5000],  # cap to avoid context overflow on small models
        revision_instructions=REVISION_INSTRUCTIONS_TEMPLATE,
    )

    critic_model   = cfg.get("critic", {}).get("model", "qwen2.5:1.5b")
    critic_temp    = cfg.get("critic", {}).get("temperature", 0.1)
    ollama_timeout = cfg.get("timeouts", {}).get("ollama_generate", 600)

    log.info("[CRITIC] %s — %s", clause_id, clause_name)
    verdict = run_reviewer_agent(cfg["llm"]["base_url"], critic_model, prompt, critic_temp, timeout=ollama_timeout)
    # Overwrite clause identity from known values rather than trusting the model's echo —
    # same anti-hallucination principle used elsewhere in this codebase.
    verdict = verdict.model_copy(update={"clause_id": clause_id, "clause_name": clause_name})
    assessment = verdict.overall_assessment
    result = verdict_to_markdown(verdict)
    log.info("[CRITIC RESULT] %s → %s", clause_id, assessment)

    critic_file.write_text(result, encoding="utf-8")
    critic_json_file.write_text(verdict.model_dump_json(indent=2), encoding="utf-8")
    return assessment, result
```

Note the prompt template no longer needs the OUTPUT FORMAT / VERDICT RULES markdown instructions since the schema now enforces structure — leave `CRITIC_PROMPT_TEMPLATE` as-is for this task (it still works, just carries some now-redundant formatting instructions harmlessly). Also update `parse_overall_assessment`'s docstring to note its new role:

Find the line `def parse_overall_assessment(critic_output):` and change the docstring immediately below it from:
```python
    """Extract the overall assessment from critic markdown output."""
```
to:
```python
    """Extract the overall assessment from critic markdown output.

    Legacy-format shim: only used as a fallback when reading a cached .critic.md
    written before the pydantic-ai migration (no .critic.json sidecar present).
    """
```

- [ ] **Step 3: Run tests, confirm green**

Run: `python -m pytest tests/test_critic.py -v`
Expected: all pass, including the two updated `TestRunCriticCacheHit` tests.

- [ ] **Step 4: Commit**

```bash
git add critic.py tests/test_critic.py
git commit -m "feat: write typed .critic.json sidecar, prefer it on cache-hit with legacy markdown fallback"
```

---

### Task 4: `get_review_verdict()` + typed-first rendering in the Review tab

**Model:** haiku (mechanical port + a signature change already fully specified by the main tool's version)

**Files:**
- Modify: `ui/core.py` — add `get_review_verdict(cid)` after `get_review_text(cid)` (currently ends at line 381)
- Modify: `ui/_pages/review.py` — `_render_reviewer_findings()` signature and body; import list; call site at (currently) line 263
- Test: `tests/test_review_findings_render.py` (new)

**Interfaces:**
- Consumes: `schemas.review.ReviewVerdict` (Task 1)
- Produces: `core.get_review_verdict(cid) -> ReviewVerdict | None`; `review._render_reviewer_findings(verdict_obj, rev_text: str) -> str` (signature changed — now takes `verdict_obj` as required first positional argument).

- [ ] **Step 1: Add `get_review_verdict()` to `ui/core.py`**

In `ui/core.py`, immediately after the `get_review_text(cid)` function (ends at line 381 today: `return f.read_text(encoding="utf-8", errors="replace") if f.exists() else None`), add:

```python

def get_review_verdict(cid):
    """Typed AI Reviewer result, if available (written alongside .critic.md since the
    pydantic-ai migration). Returns None for clauses not yet reviewed or reviewed
    before the migration (no .critic.json sidecar) — callers should fall back to
    get_review_text() + regex-free display in that case."""
    from schemas.review import ReviewVerdict
    f = OUTPUTS_DIR / f"{cid}.critic.json"
    if not f.exists():
        return None
    try:
        return ReviewVerdict.model_validate_json(f.read_text(encoding="utf-8"))
    except Exception:
        return None
```

- [ ] **Step 2: Write the failing render tests**

Create `tests/test_review_findings_render.py`:

```python
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
```

Run: `python -m pytest tests/test_review_findings_render.py -v`
Expected: FAIL — `_render_reviewer_findings()` currently takes only `rev_text`, calling it with two positional args raises `TypeError`.

- [ ] **Step 3: Update `ui/_pages/review.py` imports**

Change the `from core import (...)` block (lines 13-19 today) to add `get_review_verdict`:

```python
from core import (
    CLAUSE_NAMES, STATUS_KIND, REVIEW_RESULT, OUTPUTS_DIR, BASE_DIR,
    EXCEL_EXPORT_CLAUSES,
    get_clause_status, save_status, get_review_assessment, get_review_text,
    get_review_verdict,
    read_output, load_org, load_config, run_reviewer_subprocess,
    export_clause_to_word, export_clause_to_excel, _get_personnel_for_doc,
)
```

- [ ] **Step 4: Rewrite `_render_reviewer_findings()`**

Replace the existing `_render_reviewer_findings(rev_text: str) -> str` function (currently lines 83-156) with:

```python
def _render_reviewer_findings(verdict_obj, rev_text: str) -> str:
    """Convert AI Reviewer output into a styled task list with PASS/FAIL pills.

    Prefers a typed ReviewVerdict (post pydantic-ai migration — structurally
    guaranteed, no parsing needed). Falls back to regex-parsing rev_text's markdown
    for .critic.md files generated before the migration (no .critic.json sidecar,
    so verdict_obj is None)."""
    if verdict_obj is not None:
        findings = [
            {"dimension": f.dimension, "status": f.result, "finding": f.detail}
            for f in verdict_obj.findings
        ]
        revisions = list(verdict_obj.required_revisions)
        if verdict_obj.overall_assessment == "FAIL":
            verdict = "FAIL"
        elif verdict_obj.overall_assessment == "CONDITIONAL PASS":
            verdict = "CONDITIONAL"
        else:
            verdict = "PASS"
    else:
        findings = _parse_findings_table(rev_text) if rev_text else []
        revisions = _parse_required_revisions(rev_text) if rev_text else []
        verdict = ""
        for ln in (rev_text or "").splitlines():
            if "**Overall Assessment:**" in ln:
                up = ln.upper()
                if "FAIL" in up:
                    verdict = "FAIL"
                elif "CONDITIONAL" in up:
                    verdict = "CONDITIONAL"
                elif "PASS" in up:
                    verdict = "PASS"
                break

    out: list[str] = []

    # "What needs fixing" callout for non-PASS verdicts
    if verdict in ("FAIL", "CONDITIONAL") and revisions:
        items_html = "".join(
            f'<li style="margin-bottom:6px">{_html.escape(r)}</li>'
            for r in revisions[:3]
        )
        kind = _STATUS_PILL_KIND.get(verdict, "warn")
        out.append(
            f'<div class="finding {kind}" style="margin-bottom:12px">'
            f'<div class="f-head" style="margin-bottom:6px">'
            f'<span class="f-title">What needs fixing</span>'
            f'<span class="pill {kind}" style="font-size:11px;padding:1px 6px">'
            f'{verdict.title()}</span></div>'
            f'<ol style="margin:0;padding-left:18px;font-size:12.5px;line-height:1.5;color:var(--ink-2)">'
            f'{items_html}</ol></div>'
        )

    # Findings table → bullet/task list
    if findings:
        rows_html = ""
        for f in findings[:20]:
            up = f["status"].upper()
            if "FAIL" in up:
                kind = "err"
            elif "CONDITIONAL" in up:
                kind = "warn"
            elif "PASS" in up:
                kind = "ok"
            else:
                kind = "neutral"
            badge = pill(kind, _html.escape(f["status"]), dot=False)
            rows_html += (
                f'<li style="display:flex;gap:8px;align-items:flex-start;'
                f'padding:6px 0;border-bottom:1px solid var(--border)">'
                f'<div style="flex:1">'
                f'<div style="font-size:12px;font-weight:600;color:var(--ink-2);'
                f'margin-bottom:2px">{_html.escape(f["dimension"])}</div>'
                f'<div style="font-size:12px;color:var(--ink-2);line-height:1.4">'
                f'{_html.escape(f["finding"])}</div></div>'
                f'<div style="flex:none">{badge}</div>'
                f'</li>'
            )
        out.append(
            f'<ul style="list-style:none;margin:0;padding:0">{rows_html}</ul>'
        )
    elif not out:
        # No structured findings parsed — show plain text fallback
        snippet = _html.escape(rev_text[:600])
        out.append(
            f'<div style="font-size:12px;color:var(--ink-3);white-space:pre-wrap">'
            f'{snippet}</div>'
        )

    return "".join(out)
```

- [ ] **Step 5: Update the call site**

Find the line (currently ~line 263): `findings_html = _render_reviewer_findings(rev_text) if rev_text else ""`. Replace with:

```python
        findings_html = _render_reviewer_findings(get_review_verdict(selected), rev_text) if rev_text else ""
```

- [ ] **Step 6: Run tests, confirm green**

Run: `python -m pytest tests/test_review_findings_render.py -v`
Expected: `6 passed`

Run: `python -m pytest tests/ -q`
Expected: no regressions — count should be 105 (baseline) + new tests added so far.

- [ ] **Step 7: Commit**

```bash
git add ui/core.py ui/_pages/review.py tests/test_review_findings_render.py
git commit -m "feat: typed-first AI Reviewer rendering with legacy markdown fallback"
```

---

### Task 5: `launch.py` Ollama version check

**Model:** haiku (small, mechanical, isolated addition)

**Files:**
- Modify: `launch.py` — add `_ollama_version_supports_structured_output()` and wire it into `check_ollama()`
- Test: `tests/test_launch_ollama_version.py` (new)

**Interfaces:**
- Produces: `launch._ollama_version_supports_structured_output(version_str: str) -> bool`

- [ ] **Step 1: Write the failing test**

Create `tests/test_launch_ollama_version.py`:

```python
"""
Tests for launch.py's _ollama_version_supports_structured_output() — advisory check
that the local Ollama is new enough (0.5.0+) for grammar-constrained JSON output.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import launch


class TestOllamaVersionSupportsStructuredOutput(unittest.TestCase):
    def test_current_version_supported(self):
        self.assertTrue(launch._ollama_version_supports_structured_output("0.30.10"))

    def test_exact_minimum_version_supported(self):
        self.assertTrue(launch._ollama_version_supports_structured_output("0.5.0"))

    def test_older_version_unsupported(self):
        self.assertFalse(launch._ollama_version_supports_structured_output("0.4.9"))

    def test_much_older_version_unsupported(self):
        self.assertFalse(launch._ollama_version_supports_structured_output("0.1.0"))

    def test_unparseable_version_fails_open(self):
        # Advisory only — never block startup just because the version string was odd.
        self.assertTrue(launch._ollama_version_supports_structured_output("weird-build"))

    def test_empty_string_fails_open(self):
        self.assertTrue(launch._ollama_version_supports_structured_output(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

Run: `python -m pytest tests/test_launch_ollama_version.py -v`
Expected: FAIL — `AttributeError: module 'launch' has no attribute '_ollama_version_supports_structured_output'`

- [ ] **Step 2: Add the function and wire it into `check_ollama()`**

In `launch.py`, add this function immediately before `def check_ollama():` (currently at line 84):

```python
_MIN_STRUCTURED_OUTPUT_VERSION = (0, 5, 0)


def _ollama_version_supports_structured_output(version_str):
    """Ollama v0.5.0+ enforces format=json_schema via grammar-constrained decoding —
    the AI Reviewer relies on this. Returns True when unparseable (fail open — this
    is an advisory warning, not a hard requirement check)."""
    try:
        parts = tuple(int(p) for p in version_str.split(".")[:3])
        return parts >= _MIN_STRUCTURED_OUTPUT_VERSION
    except (ValueError, AttributeError):
        return True
```

Then inside `check_ollama()`, immediately after the line `log.info("Ollama running  OK  (models: %s)", ', '.join(models) if models else 'none pulled yet')`, insert:

```python
        try:
            v = requests.get(f"{base_url}/api/version", timeout=3).json().get("version", "")
            if v and not _ollama_version_supports_structured_output(v):
                log.warning(
                    "Ollama %s is older than 0.5.0 — structured AI Reviewer output "
                    "may not be enforced. Consider upgrading: https://ollama.com/download", v
                )
        except Exception:
            pass  # advisory only — never block startup on this
```

- [ ] **Step 3: Run tests, confirm green**

Run: `python -m pytest tests/test_launch_ollama_version.py -v`
Expected: `6 passed`

- [ ] **Step 4: Commit**

```bash
git add launch.py tests/test_launch_ollama_version.py
git commit -m "feat: warn when local Ollama predates structured-output support"
```

---

### Task 6: Phase 1 devsecops checkpoint

**Model:** sonnet (code-review judgment)

**Files:** none created — review + verify only.

- [ ] **Step 1: Dispatch a code-review pass**

Invoke the `code-review` skill (or equivalent review agent) against the diff introduced by Tasks 1-5 (`schemas/`, `adapters/`, `critic.py`, `ui/core.py`, `ui/_pages/review.py`, `launch.py`, `requirements.txt`, and their tests). Ask it to specifically check:
- The offline invariant (base_url `/v1` construction, hardcoded `api_key="ollama"`, fail-loud on empty base_url) is preserved exactly as specified in Task 2.
- No leftover dead code (`call_ollama()` in `critic.py` is still used elsewhere — confirm; if unused after this phase, that's expected to be flagged and left for a later cleanup pass, not deleted here, since `parse_overall_assessment()` still depends on nothing from `call_ollama()` but `call_ollama()` itself may still be referenced by `pipeline.py`'s own reviewer-independent generation calls — verify before removing anything).
- `_render_reviewer_findings()`'s new required `verdict_obj` parameter doesn't break any other caller besides the one call site updated in Task 4, Step 5.

Fix any findings inline.

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: all tests pass, count ≥ 105 (baseline) + tests added in Tasks 1-5 (30 new: 9 schema + 9 adapter + 3 new critic classes ≈ 8 tests + 6 render + 6 launch — exact new count depends on Step 1 findings; confirm no failures, not an exact number).

- [ ] **Step 3: Commit the checkpoint** (only if Step 1 produced fixes; otherwise this is a no-op — Tasks 1-5 are already committed individually)

```bash
git add -A
git commit -m "fix: address Phase 1 code-review findings" --allow-empty
```

(Use `--allow-empty` only if there is genuinely nothing to commit and you want a marker commit for the checkpoint; otherwise omit `--allow-empty` and only run this if there are actual changes.)

---

## PHASE 2 — Org/personnel extraction → pydantic-ai

### Task 7: Typed OrgProfile schema

**Model:** haiku (verbatim port, already field-verified against demo's `ORG_JSON_SCHEMA` — no drift found)

**Files:**
- Create: `schemas/org_profile.py`
- Test: `tests/test_org_profile_schema.py`

**Interfaces:**
- Produces: `schemas.org_profile.OrgProfile`, `PersonnelEntry`, `AssetEntry`, `StakeholderEntry`. Task 8/9 consume these.

- [ ] **Step 1: Create the schema**

Create `schemas/org_profile.py`:

```python
"""Typed org profile / personnel extraction output — replaces the manual
raw.find("{")...json.loads() slicing in ui/core.py's extract_org_with_llm()
and extract_personnel_with_llm(). Fields mirror ui/core.py's ORG_JSON_SCHEMA dict
1:1 — see tests/test_org_profile_schema.py for the field-drift guard.
"""

from pydantic import BaseModel, Field


class StakeholderEntry(BaseModel):
    name: str = ""
    expectation: str = ""


class AssetEntry(BaseModel):
    name: str = ""
    system: str = ""
    owner: str = ""
    classification: str = ""


class PersonnelEntry(BaseModel):
    role: str = Field(
        default="",
        description="Job title or information-security governance role, e.g. CEO, CISO, IT Manager, DPO — NOT the person's name",
    )
    name: str = Field(
        default="",
        description="Full name of the person holding this role — NOT the job title",
    )


class OrgProfile(BaseModel):
    name: str = ""
    industry: str = ""
    size: str = ""
    scope: str = ""
    primary_processes: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    regulatory_drivers: list[str] = Field(default_factory=list)
    legal_basis: list[str] = Field(default_factory=list)
    stakeholders: list[StakeholderEntry] = Field(default_factory=list)
    assets: list[AssetEntry] = Field(default_factory=list)
    key_personnel: list[PersonnelEntry] = Field(default_factory=list)
    critical_suppliers: list[str] = Field(default_factory=list)
    existing_controls: list[str] = Field(default_factory=list)
    certifications_existing: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Write the field-drift guard test**

Create `tests/test_org_profile_schema.py`:

```python
"""
Tests for schemas/org_profile.py — OrgProfile / PersonnelEntry structural guarantees,
and the field-drift guard against ui/core.py's legacy ORG_JSON_SCHEMA dict.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas.org_profile import AssetEntry, OrgProfile, PersonnelEntry, StakeholderEntry


class TestOrgProfileDefaults(unittest.TestCase):
    def test_all_fields_default_without_arguments(self):
        # Downstream code does unconditional org.get(key, []) with no None-checks —
        # every field must have a usable default, never None.
        profile = OrgProfile()
        self.assertEqual(profile.name, "")
        self.assertEqual(profile.primary_processes, [])
        self.assertEqual(profile.stakeholders, [])
        self.assertEqual(profile.assets, [])
        self.assertEqual(profile.key_personnel, [])

    def test_no_field_is_optional_none(self):
        for field in OrgProfile.model_fields.values():
            self.assertNotIn("NoneType", str(field.annotation))

    def test_nested_entries_construct(self):
        profile = OrgProfile(
            name="Acme",
            stakeholders=[StakeholderEntry(name="Regulator", expectation="Compliance")],
            assets=[AssetEntry(name="ERP", system="SAP", owner="IT", classification="Confidential")],
            key_personnel=[PersonnelEntry(role="CEO", name="Jane Doe")],
        )
        self.assertEqual(profile.stakeholders[0].expectation, "Compliance")
        self.assertEqual(profile.assets[0].system, "SAP")
        self.assertEqual(profile.key_personnel[0].name, "Jane Doe")

    def test_model_dump_round_trips_to_plain_dict(self):
        profile = OrgProfile(name="Acme", locations=["Berlin"])
        dumped = profile.model_dump()
        self.assertIsInstance(dumped, dict)
        self.assertEqual(dumped["name"], "Acme")
        self.assertEqual(dumped["locations"], ["Berlin"])


class TestOrgProfileMatchesLegacySchema(unittest.TestCase):
    def test_fields_match_legacy_org_json_schema_keys(self):
        # Field-drift guard: if a future session adds a field to one but not the
        # other, this fails loudly instead of silently diverging.
        sys.path.insert(0, str(Path(__file__).parent.parent / "ui"))
        import core

        self.assertEqual(set(OrgProfile.model_fields.keys()), set(core.ORG_JSON_SCHEMA.keys()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 3: Run tests, confirm green**

Run: `python -m pytest tests/test_org_profile_schema.py -v`
Expected: `5 passed`

- [ ] **Step 4: Commit**

```bash
git add schemas/org_profile.py tests/test_org_profile_schema.py
git commit -m "feat: add typed OrgProfile schema, field-verified against ORG_JSON_SCHEMA"
```

---

### Task 8: Split `extract_org_with_llm` into agent-call + thin wrapper

**Model:** sonnet (replaces manual JSON-slicing with agent call — real logic change)

**Files:**
- Modify: `ui/core.py` — replace `extract_org_with_llm(text, cfg)` (currently lines 972-1029) with a shared agent-builder + `_extract_org_agent_call()` + thin `extract_org_with_llm()`
- Test: `tests/test_org_extraction.py` (new — created fully in this task, extended in Task 9)

**Interfaces:**
- Consumes: `schemas.org_profile.OrgProfile` (Task 7)
- Produces: `core._build_extraction_agent(cfg, output_type, num_predict, timeout) -> Agent`, `core._extract_org_agent_call(text, cfg) -> OrgProfile`, `core.extract_org_with_llm(text, cfg) -> dict | None` (public signature unchanged — callers in `ui/_pages/organization.py` need no changes)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_org_extraction.py`:

```python
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
```

Run: `python -m pytest tests/test_org_extraction.py -v`
Expected: FAIL — `core._extract_org_agent_call` does not exist yet.

- [ ] **Step 2: Add pydantic-ai imports and `_build_extraction_agent()` to `ui/core.py`**

Add these imports near the top of `ui/core.py`, after the existing `import yaml` line:

```python
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from schemas.org_profile import OrgProfile, PersonnelEntry
```

Add this shared builder function immediately before the current `extract_org_with_llm` (i.e. right before line 972):

```python
def _build_extraction_agent(cfg, output_type, num_predict, timeout):
    provider = OpenAIProvider(base_url=f"{cfg['llm']['base_url']}/v1", api_key="ollama")
    model = OpenAIChatModel(
        cfg["llm"]["model"],
        provider=provider,
        settings=ModelSettings(temperature=0.05, max_tokens=num_predict, timeout=timeout),
    )
    return Agent(model, output_type=NativeOutput(output_type))
```

- [ ] **Step 3: Replace `extract_org_with_llm` (currently lines 972-1029)**

Replace the entire function (including the `ORG_JSON_SCHEMA`-based prompt-building block and the raw `requests.post` + manual `raw.find("{")...json.loads()` slicing) with:

```python
def _extract_org_agent_call(text, cfg) -> OrgProfile:
    """Pure agent call, no Streamlit — testable in isolation."""
    prompt = f"""You are an ISO 27001 consultant. Extract organization information from the document below.

Rules:
- "scope": 1–2 sentences describing the core business and IT activities suitable for an ISMS scope statement
- "size": format as "45 employees" or "~100 employees" if approximate
- "departments": list department or team names found in the document (e.g. ["R&D", "Sales", "HR"])
- "regulatory_drivers": regulations or standards driving ISMS (e.g. ["GDPR", "NIS2", "TISAX"])
- "legal_basis": include only regulations explicitly mentioned in the document — do NOT invent
- "existing_controls": list specific security controls mentioned (MFA, VPN, firewalls, encryption, etc.)
- Leave fields as empty string or empty list when not found in the document
- Do NOT invent information

DOCUMENT:
{text[:5000]}"""
    agent = _build_extraction_agent(cfg, OrgProfile, num_predict=1500, timeout=300)
    return agent.run_sync(prompt).output


def extract_org_with_llm(text, cfg):
    try:
        requests.get(f"{cfg['llm']['base_url']}/api/tags", timeout=5)
    except Exception:
        st.error("Cannot reach the AI engine. "
                 "Go to Organization > AI Engine and check that Ollama is running.")
        return None

    try:
        return _extract_org_agent_call(text, cfg).model_dump()
    except Exception as e:
        st.error(f"Extraction error: {e}")
        return None
```

Note `ORG_JSON_SCHEMA` (currently lines 961-969) stays untouched — `ui/_pages/organization.py` still uses it for form rendering (confirmed by the spec's field-drift guard in Task 7).

- [ ] **Step 4: Run tests, confirm the org tests pass**

Run: `python -m pytest tests/test_org_extraction.py -v -k Org`
Expected: `4 passed` (personnel tests still fail until Task 9)

- [ ] **Step 5: Commit**

```bash
git add ui/core.py tests/test_org_extraction.py
git commit -m "feat: replace manual JSON-slicing org extraction with typed pydantic-ai agent"
```

---

### Task 9: Split `extract_personnel_with_llm` into agent-call + thin wrapper

**Model:** sonnet (same reasoning as Task 8 — real logic replacement)

**Files:**
- Modify: `ui/core.py` — replace `extract_personnel_with_llm(text, cfg)` (currently lines 1032-1065)
- Modify: `tests/test_org_extraction.py` — add personnel test classes

**Interfaces:**
- Consumes: `schemas.org_profile.PersonnelEntry` (Task 7), `core._build_extraction_agent()` (Task 8)
- Produces: `core._extract_personnel_agent_call(text, cfg) -> list[PersonnelEntry]`, `core.extract_personnel_with_llm(text, cfg) -> list[dict] | None` (public signature unchanged)

- [ ] **Step 1: Add the failing personnel tests**

Append to `tests/test_org_extraction.py`, before the `if __name__ == "__main__":` line:

```python
class TestExtractPersonnelAgentCall(unittest.TestCase):
    def test_returns_list_of_personnel_entries(self):
        canned = [PersonnelEntry(role="CEO", name="Jane Doe")]
        with patch("core.Agent") as mock_agent_cls, patch("core.OpenAIProvider"):
            mock_agent_cls.return_value.run_sync.return_value.output = canned
            result = core._extract_personnel_agent_call("some org chart text", CFG)
        self.assertEqual(result, canned)


class TestExtractPersonnelWithLlm(unittest.TestCase):
    def test_success_returns_plain_dicts(self):
        canned = [PersonnelEntry(role="CEO", name="Jane Doe"), PersonnelEntry(role="CISO", name="John Smith")]
        with patch("core._extract_personnel_agent_call", return_value=canned):
            result = core.extract_personnel_with_llm("doc text", CFG)
        self.assertEqual(result, [{"role": "CEO", "name": "Jane Doe"}, {"role": "CISO", "name": "John Smith"}])

    def test_failure_shows_error_and_returns_none(self):
        with patch("core._extract_personnel_agent_call", side_effect=RuntimeError("boom")), \
             patch("core.st.error") as mock_error:
            result = core.extract_personnel_with_llm("doc text", CFG)
        self.assertIsNone(result)
        mock_error.assert_called_once()
```

Run: `python -m pytest tests/test_org_extraction.py -v -k Personnel`
Expected: FAIL — `core._extract_personnel_agent_call` does not exist yet.

- [ ] **Step 2: Replace `extract_personnel_with_llm` (currently lines 1032-1065)**

Replace the entire function with:

```python
def _extract_personnel_agent_call(text, cfg) -> list[PersonnelEntry]:
    """Pure agent call, no Streamlit — testable in isolation."""
    prompt = f"""You are an ISO 27001 consultant. Extract key personnel information from the document below.

Rules:
- Include only named individuals with clear roles
- Roles should map to information security governance (CEO, CISO, IT Manager, Risk Owner, DPO, etc.)
- Return an empty list if no clear personnel found
- Do NOT invent names
- Keep role and name in separate fields — never combine them into one string

DOCUMENT:
{text[:3000]}"""
    agent = _build_extraction_agent(cfg, list[PersonnelEntry], num_predict=300, timeout=120)
    return agent.run_sync(prompt).output


def extract_personnel_with_llm(text, cfg):
    """Extract key personnel names and roles from an org chart or document."""
    try:
        entries = _extract_personnel_agent_call(text, cfg)
        return [e.model_dump() for e in entries]
    except Exception as e:
        st.error(f"Personnel extraction error: {e}")
        return None
```

- [ ] **Step 3: Run the full extraction test file**

Run: `python -m pytest tests/test_org_extraction.py -v`
Expected: `7 passed`

- [ ] **Step 4: Commit**

```bash
git add ui/core.py tests/test_org_extraction.py
git commit -m "feat: replace manual JSON-slicing personnel extraction with typed pydantic-ai agent"
```

---

### Task 10: Phase 2 devsecops checkpoint

**Model:** sonnet

**Files:** none created — review + verify only.

- [ ] **Step 1: Dispatch a code-review pass**

Review the diff from Tasks 7-9. Specifically check:
- `_build_extraction_agent()` uses the same hardened offline-invariant construction as `critic.py`'s `run_reviewer_agent()` (`.../v1`, `api_key="ollama"`). If it does not also fail loud on an empty `base_url`, add the same guard used in Task 2, Step 3, and a matching test in `tests/test_org_extraction.py` mirroring `TestReviewerAgentNoCloudApi` from Task 2.
- `ORG_JSON_SCHEMA` in `ui/core.py` is still used (by `ui/_pages/organization.py`) and was not accidentally removed.
- Public function signatures (`extract_org_with_llm`, `extract_personnel_with_llm`) are unchanged so no caller in `ui/_pages/organization.py` needs updates.

Fix any findings inline (in particular, add the empty-base_url guard if missing — this is a genuine gap since Task 8/9 as written above do not duplicate that check).

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: all green, count increased by the tests added in Tasks 7-9 (5 schema + 7 extraction = 12 new, plus any added during the Step 1 review fix).

- [ ] **Step 3: Commit the checkpoint** (only if Step 1 produced fixes)

```bash
git add -A
git commit -m "fix: address Phase 2 code-review findings — offline invariant on extraction agent"
```

---

## PHASE 4 — Model catalog split

*(Phase 3 — rigid per-clause schemas — is explicitly out of scope; see spec. No tasks for it.)*

### Task 11: `models_catalog.json` + `setup_config.py` `_TIER_TUNING`/catalog split

**Model:** sonnet (the highest-risk task in this plan — must produce byte-identical `TIERS` behavior from a full rewrite of a currently fully-hardcoded structure)

**Files:**
- Create: `models_catalog.json`
- Modify: `setup_config.py` — replace hardcoded `TIERS` (currently lines 29-148, including the `LEGACY_FACTORY_MODELS` set at lines 143-148) with `_TIER_TUNING` + `load_models_catalog()` + `_build_tiers()` + `_build_legacy_factory_models()` + `TIERS = _build_tiers()` + `LEGACY_FACTORY_MODELS = _build_legacy_factory_models()`
- Modify: `tests/test_setup_config.py` — add `TestModelsCatalogFile` class

**Interfaces:**
- Produces: `setup_config.load_models_catalog(path=None) -> dict`, `setup_config.TIERS` (same list-of-14-key-dicts shape as before — every existing reader, e.g. `select_tier()`, `apply_to_config()`, must see identical keys), `setup_config.LEGACY_FACTORY_MODELS` (same `set[str]` shape as before)

- [ ] **Step 1: Create `models_catalog.json`**

Create `models_catalog.json` at the project root:

```json
{
  "catalog_version": "2026.07",
  "tiers": {
    "high": {
      "gen_model": "gemma4:12b-it-qat",
      "reviewer_model": "qwen2.5:1.5b",
      "label": "High-end (12 GB+ VRAM)",
      "why": "12 GB+ VRAM fits a 7.2 GB generator fully on the GPU.",
      "speed": "~1-2 min per document"
    },
    "mid": {
      "gen_model": "gemma4:e4b-it-qat",
      "reviewer_model": "qwen2.5:1.5b",
      "label": "Mid-range (6-12 GB VRAM)",
      "why": "6-12 GB VRAM fits a 6.1 GB generator on the GPU.",
      "speed": "~2-4 min per document"
    },
    "cpu_rich": {
      "gen_model": "phi4-mini:3.8b-q4_K_M",
      "reviewer_model": "qwen2.5:1.5b",
      "label": "CPU-rich (16 GB+ RAM, < 6 GB VRAM)",
      "why": "Plenty of RAM but the GPU is too small for a big model; a small fast generator on CPU beats a big one spilling.",
      "speed": "~8-15 min per document"
    },
    "low": {
      "gen_model": "phi4-mini:3.8b-q4_K_M",
      "reviewer_model": "qwen2.5:1.5b",
      "label": "Standard (8-16 GB RAM)",
      "why": "Limited RAM; a 2.5 GB generator is the safe fit.",
      "speed": "~10-20 min per document"
    },
    "minimal": {
      "gen_model": "qwen2.5:1.5b",
      "reviewer_model": "qwen2.5:1.5b",
      "label": "Minimal (< 8 GB RAM, CPU-only)",
      "why": "Very low RAM; the smallest model is the only safe choice.",
      "speed": "~5-10 min per document"
    }
  },
  "legacy_tags": [
    "gemma4:12b-it-qat",
    "gemma4:e4b-it-qat",
    "phi4-mini:3.8b-q4_K_M",
    "qwen2.5:1.5b",
    "gemma4:e2b-it-qat",
    "mistral:7b-q4_K_M",
    "llama3.2:3b-q4_K_M"
  ]
}
```

This is byte-identical in tier identity to demo's current hardcoded `TIERS` (verified against demo's actual file: same 5 tier names, same `gen_model`/`reviewer_model`/`label`/`why`/`speed` values for each).

- [ ] **Step 2: Write the failing catalog tests**

Add to `tests/test_setup_config.py`, before the final `if __name__ == "__main__":` block (check the existing import block at the top already has `import json` and `import tempfile` — if not, add them alongside the existing `import sys` / `unittest` / `Path` imports, and add `from unittest.mock import MagicMock, patch`):

```python
class TestModelsCatalogFile(unittest.TestCase):
    """The bundled models_catalog.json is the source of truth for gen_model/
    reviewer_model/label/why/speed — TIERS merges it at import time with the
    Python-side hardware-tuning fields (min_ram_gb, min_vram_gb, timeouts, etc.)."""

    def test_bundled_catalog_has_all_five_tiers(self):
        catalog = setup_config.load_models_catalog()
        self.assertEqual(
            set(catalog["tiers"].keys()),
            {"high", "mid", "cpu_rich", "low", "minimal"},
        )

    def test_bundled_catalog_tier_entries_have_required_keys(self):
        catalog = setup_config.load_models_catalog()
        required = {"gen_model", "reviewer_model", "label", "why", "speed"}
        for name, entry in catalog["tiers"].items():
            missing = required - set(entry.keys())
            self.assertEqual(missing, set(), f"catalog tier '{name}' missing keys: {missing}")

    def test_bundled_catalog_has_legacy_tags(self):
        catalog = setup_config.load_models_catalog()
        self.assertIn("legacy_tags", catalog)
        self.assertIn("gemma4:e2b-it-qat", catalog["legacy_tags"])

    def test_tiers_merged_from_catalog_keep_full_shape(self):
        # Every tier dict must still carry both the catalog fields AND the
        # Python-side tuning fields — same contract downstream code relies on.
        for tier in setup_config.TIERS:
            for key in ("gen_model", "reviewer_model", "label", "why", "speed",
                        "min_ram_gb", "min_vram_gb", "ollama_timeout",
                        "model_swap_delay", "num_predict", "item_counts"):
                self.assertIn(key, tier, f"tier '{tier.get('name')}' missing '{key}' after merge")

    def test_legacy_factory_models_derived_from_catalog(self):
        catalog = setup_config.load_models_catalog()
        expected = set(catalog["legacy_tags"])
        for tier in catalog["tiers"].values():
            expected.add(tier["gen_model"])
            expected.add(tier["reviewer_model"])
        self.assertEqual(setup_config.LEGACY_FACTORY_MODELS, expected)
```

Run: `python -m pytest tests/test_setup_config.py::TestModelsCatalogFile -v`
Expected: FAIL — `setup_config.load_models_catalog` does not exist yet.

- [ ] **Step 3: Replace the hardcoded `TIERS`/`LEGACY_FACTORY_MODELS` in `setup_config.py`**

Add `import json` to the existing import block at the top of `setup_config.py` (currently: `argparse`, `platform`, `subprocess`, `sys`, `Path`, `yaml` — no `json` yet).

Add this constant right after `CONFIG_PATH = BASE_DIR / "config.yaml"`:

```python
_CATALOG_PATH = BASE_DIR / "models_catalog.json"
_ONLINE_CACHE_PATH = BASE_DIR / "models_catalog.online_cache.json"
```

Replace the entire block from `TIERS = [` (currently line 29) through the closing `}` of `LEGACY_FACTORY_MODELS` (currently line 148) with:

```python
# ---------------------------------------------------------------------------
# Hardware tiers - ordered best to worst, first match wins (see select_tier).
#
# Rule: VRAM-fit first. A model only earns a GPU tier if it FITS that card's
# VRAM; a model spilled to CPU runs 5-10x slower, so low-VRAM machines get a
# small fast generator - never a big spilling one. RAM alone never qualifies
# for a big model (32 GB RAM + no GPU still generates at CPU speed).
#
# Model identity (gen_model/reviewer_model/label/why/speed) lives in
# models_catalog.json, a bundled+versioned JSON file — this keeps the model
# picks maintainer-updatable without touching this module. Hardware-tuning
# fields below (thresholds, timeouts, output length) stay in Python since
# they're install-time behavior decisions tightly coupled to this codebase,
# not model facts.
# ---------------------------------------------------------------------------
_TIER_TUNING = [
    {
        "name":              "high",
        "min_ram_gb":        0,
        "min_vram_gb":       12,
        "ollama_timeout":    120,
        "model_swap_delay":  2,
        "num_gpu":           1,
        "num_predict":       2000,
        "length_profile":    "comprehensive (~1200-1800 words)",
        "item_counts": {
            "min_risks": 5, "risk_range": "5-7",
            "min_objectives": 5, "obj_range": "5-7",
            "min_metrics": 6, "metric_range": "6-8",
            "min_improvements": 3, "table_note": "",
        },
    },
    {
        "name":              "mid",
        "min_ram_gb":        0,
        "min_vram_gb":       6,
        "ollama_timeout":    240,
        "model_swap_delay":  4,
        "num_gpu":           1,
        "num_predict":       2000,
        "length_profile":    "comprehensive (~1200-1800 words)",
        "item_counts": {
            "min_risks": 5, "risk_range": "5-7",
            "min_objectives": 5, "obj_range": "5-7",
            "min_metrics": 6, "metric_range": "6-8",
            "min_improvements": 3, "table_note": "",
        },
    },
    {
        "name":              "cpu_rich",
        "min_ram_gb":        16,
        "min_vram_gb":       0,
        "ollama_timeout":    600,
        "model_swap_delay":  12,
        "num_gpu":           1,
        "num_predict":       1200,
        "length_profile":    "concise but complete (~500-800 words)",
        "item_counts": {
            "min_risks": 3, "risk_range": "3-4",
            "min_objectives": 4, "obj_range": "4-5",
            "min_metrics": 4, "metric_range": "4-6",
            "min_improvements": 3, "table_note": " Keep tables to 3-5 rows.",
        },
    },
    {
        "name":              "low",
        "min_ram_gb":        8,
        "min_vram_gb":       0,
        "ollama_timeout":    900,
        "model_swap_delay":  16,
        "num_gpu":           1,
        "num_predict":       1200,
        "length_profile":    "concise but complete (~500-800 words)",
        "item_counts": {
            "min_risks": 3, "risk_range": "3-4",
            "min_objectives": 4, "obj_range": "4-5",
            "min_metrics": 4, "metric_range": "4-6",
            "min_improvements": 3, "table_note": " Keep tables to 3-5 rows.",
        },
    },
    {
        "name":              "minimal",
        "min_ram_gb":        0,
        "min_vram_gb":       0,
        "ollama_timeout":    900,
        "model_swap_delay":  20,
        "num_gpu":           0,
        "num_predict":       1000,
        "length_profile":    "concise (~400-600 words)",
        "item_counts": {
            "min_risks": 3, "risk_range": "3-4",
            "min_objectives": 4, "obj_range": "4-5",
            "min_metrics": 4, "metric_range": "4-6",
            "min_improvements": 3, "table_note": " Keep tables to 3-5 rows.",
        },
    },
]


def load_models_catalog(path=None):
    """Load the bundled (or an override) models catalog JSON."""
    p = Path(path) if path else _CATALOG_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _build_tiers():
    """Merge _TIER_TUNING (Python, hardware behavior) with models_catalog.json
    (model identity) into the full tier dicts the rest of this module expects."""
    catalog = load_models_catalog()
    tiers = []
    for tuning in _TIER_TUNING:
        entry = catalog["tiers"][tuning["name"]]
        merged = dict(tuning)
        merged.update({
            "gen_model": entry["gen_model"],
            "reviewer_model": entry["reviewer_model"],
            "label": entry["label"],
            "why": entry["why"],
            "speed": entry["speed"],
        })
        tiers.append(merged)
    return tiers


def _build_legacy_factory_models():
    """Factory model tags that apply_to_config() is allowed to overwrite on
    re-detection: current tier models plus every models_catalog.json legacy_tags
    entry (older factory defaults, appended over time, never removed) — so an
    install that picked an old default migrates cleanly. A tag a user typed by
    hand is NOT in this set and is left untouched."""
    catalog = load_models_catalog()
    tags = set(catalog.get("legacy_tags", []))
    for entry in catalog["tiers"].values():
        tags.add(entry["gen_model"])
        tags.add(entry["reviewer_model"])
    return tags


TIERS = _build_tiers()
LEGACY_FACTORY_MODELS = _build_legacy_factory_models()
```

- [ ] **Step 4: Run tests, confirm green and confirm no downstream regression**

Run: `python -m pytest tests/test_setup_config.py -v`
Expected: all pass, including the pre-existing `TestSelectTier`, `TestLegacyFactoryModels`, `TestTierOutputLengthFields`, `TestApplyToConfigWritesNumPredict`, `TestItemCountsStructure` classes (these read `setup_config.TIERS`/`LEGACY_FACTORY_MODELS` and must see the identical shape post-merge — if any of these fail, the merge in Step 3 dropped a key).

Run: `python setup_config.py --detect`
Expected: identical output to before this task's changes (same tier chosen, same why/speed/model strings) — this is a byte-identical output check, compare manually against a `--detect` run captured before Step 3.

Run: `python setup_config.py --print-models`
Expected: unchanged 2-line contract (gen model tag, then reviewer model tag) that `install.bat` depends on.

- [ ] **Step 5: Commit**

```bash
git add models_catalog.json setup_config.py tests/test_setup_config.py
git commit -m "feat: split setup_config.py TIERS into models_catalog.json + _TIER_TUNING"
```

---

### Task 12: `refresh_catalog_best_effort()` + `.gitignore`

**Model:** haiku (isolated, fully fail-safe function; mechanical port)

**Files:**
- Modify: `setup_config.py` — add `refresh_catalog_best_effort()` and a `--refresh-catalog` CLI flag
- Modify: `.gitignore` — add `models_catalog.online_cache.json`
- Modify: `tests/test_setup_config.py` — add `TestRefreshCatalogBestEffort`

**Interfaces:**
- Produces: `setup_config.refresh_catalog_best_effort() -> None` (never raises, opt-in CLI only)

- [ ] **Step 1: Add the `.gitignore` entry**

Modify `.gitignore` — add this line under the existing `# VaultISO27 runtime` section (after `inputs/organization_data.json`):

```
models_catalog.online_cache.json
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_setup_config.py`, after `TestModelsCatalogFile` and before `if __name__ == "__main__":`. Confirm `import tempfile` and `from unittest.mock import MagicMock, patch` are present at the top of the file (add if missing):

```python
class TestRefreshCatalogBestEffort(unittest.TestCase):
    """refresh_catalog_best_effort() is opt-in, never called from main()'s install
    path, and must never raise or touch the bundled models_catalog.json — only
    ever writes a separate online-cache file on success."""

    def test_network_failure_never_raises(self):
        with patch("setup_config.requests.get", side_effect=Exception("offline")):
            try:
                setup_config.refresh_catalog_best_effort()
            except Exception as e:
                self.fail(f"refresh_catalog_best_effort() raised on network failure: {e}")

    def test_network_failure_does_not_touch_bundled_catalog(self):
        original = setup_config._CATALOG_PATH.read_text(encoding="utf-8")
        with patch("setup_config.requests.get", side_effect=Exception("offline")):
            setup_config.refresh_catalog_best_effort()
        self.assertEqual(setup_config._CATALOG_PATH.read_text(encoding="utf-8"), original)

    def test_malformed_response_never_raises(self):
        mock_resp = MagicMock()
        mock_resp.json.side_effect = ValueError("not json")
        with patch("setup_config.requests.get", return_value=mock_resp):
            try:
                setup_config.refresh_catalog_best_effort()
            except Exception as e:
                self.fail(f"refresh_catalog_best_effort() raised on malformed response: {e}")

    def test_success_writes_separate_cache_file_not_bundled(self):
        original_bundled = setup_config._CATALOG_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "models_catalog.online_cache.json"
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"models": [{"name": "some-new-model:1b"}]}
            with patch("setup_config.requests.get", return_value=mock_resp), \
                 patch("setup_config._ONLINE_CACHE_PATH", cache_path):
                setup_config.refresh_catalog_best_effort()
            self.assertTrue(cache_path.exists())
        self.assertEqual(setup_config._CATALOG_PATH.read_text(encoding="utf-8"), original_bundled)
```

Run: `python -m pytest tests/test_setup_config.py::TestRefreshCatalogBestEffort -v`
Expected: FAIL — `setup_config.requests` does not exist (no `import requests` yet) and `refresh_catalog_best_effort` is undefined.

- [ ] **Step 3: Add `import requests` and `refresh_catalog_best_effort()`**

Add `import requests` to the top import block of `setup_config.py` (alongside `import yaml`).

Add this function immediately after `_build_legacy_factory_models()` and before `TIERS = _build_tiers()`:

```python
def refresh_catalog_best_effort():
    """Opt-in, manual-only (CLI --refresh-catalog), never called from install's
    default path. Best-effort GET to a public Ollama model index; on ANY failure
    (offline, timeout, malformed response, unexpected schema) this is a silent
    no-op — never raises, never touches the bundled models_catalog.json. On
    success, writes an informational cache file only; does not alter TIERS
    or LEGACY_FACTORY_MODELS for the current process."""
    try:
        resp = requests.get("https://ollamadb.dev/api/v1/models", timeout=5)
        if resp.status_code != 200:
            return
        data = resp.json()
        if not isinstance(data, dict) or "models" not in data:
            return
        _ONLINE_CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"  [OK] Online model index cached to {_ONLINE_CACHE_PATH.name} "
              "(informational only — config.yaml is unaffected).")
    except Exception:
        pass  # advisory only — never block or fail install on this
```

- [ ] **Step 4: Wire the `--refresh-catalog` CLI flag**

In `setup_config.py`'s `if __name__ == "__main__":` block (currently near the bottom, after the `--print-models` and `--detect` argparse arguments), add a new mutually-independent flag:

```python
    parser.add_argument(
        "--refresh-catalog", action="store_true",
        help="Best-effort check for newer model tags against a public index. Never touches "
             "models_catalog.json or config.yaml; writes an informational cache file only.",
    )
```

And add the corresponding branch (before the final `else: main()`):

```python
    if args.refresh_catalog:
        refresh_catalog_best_effort()
```

- [ ] **Step 5: Run tests, confirm green**

Run: `python -m pytest tests/test_setup_config.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add setup_config.py .gitignore tests/test_setup_config.py
git commit -m "feat: add opt-in refresh_catalog_best_effort() and --refresh-catalog flag"
```

---

### Task 13: Phase 4 devsecops checkpoint

**Model:** sonnet (byte-identical-output verification requires careful comparison, not just "tests pass")

**Files:** none created — review + verify only.

- [ ] **Step 1: Dispatch a code-review pass**

Review the diff from Tasks 11-12. Specifically check:
- No downstream code outside `setup_config.py` reads the old flat `TIERS` structure in a way that breaks with the merge (grep for `TIERS` usage across `ui/_pages/organization.py`, `install.bat`-invoked calls, etc. — confirm all reads go through the same key names as before).
- `refresh_catalog_best_effort()` is genuinely never invoked from `main()`'s default install path (grep `refresh_catalog_best_effort(` — should appear exactly twice: its `def` and the `--refresh-catalog` CLI branch).

- [ ] **Step 2: Byte-identical output verification**

Run (capture output before and after Task 11 if not already captured):

```bash
python setup_config.py --detect
python setup_config.py --print-models
```

Expected: both produce output identical to the pre-Task-11 baseline (same tier name, same why/speed/model strings, same 2-line `--print-models` contract).

- [ ] **Step 3: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: all green.

- [ ] **Step 4: Commit the checkpoint** (only if Step 1 produced fixes)

```bash
git add -A
git commit -m "fix: address Phase 4 code-review findings"
```

---

## FINAL — Integration + user acceptance verification

### Task 14: Real-Ollama integration smoke test + manual dashboard verification

**Model:** sonnet (interpreting real generation output quality is judgment, not mechanical)

**Files:** none — verification only, run in the main session or by a human, not delegated to a subagent (requires a running Ollama and visual judgment of the dashboard).

- [ ] **Step 1: Full pytest baseline**

Run: `python -m pytest tests/ -q`
Expected: all green, final count = 105 (original baseline) + all tests added across Tasks 1-12.

- [ ] **Step 2: Integration smoke test — Reviewer, fast model**

With Ollama running and `qwen2.5:1.5b` pulled, run against a real generated clause (adjust `4.3` to any clause with an existing `outputs/4.3.md`):

```bash
python critic.py --clause 4.3 --force
```

Expected: completes without error, `outputs/4.3.critic.md` and `outputs/4.3.critic.json` both written, `.critic.json` parses as a valid `ReviewVerdict` (open it and confirm `overall_assessment` is one of PASS/CONDITIONAL PASS/FAIL, `findings` has exactly 5 entries).

- [ ] **Step 3: Integration smoke test — org extraction, fast model temporarily**

Manually verify `extract_org_with_llm()` against a short sample text via a Python shell (from project root, venv active):

```bash
python -c "
import sys; sys.path.insert(0, 'ui')
import core
cfg = {'llm': {'base_url': 'http://localhost:11434', 'model': 'qwen2.5:1.5b'}}
result = core.extract_org_with_llm('Acme Corp is a 50-employee manufacturing company based in Berlin, subject to GDPR.', cfg)
print(result)
"
```

Expected: prints a dict with `name`/`industry`/`locations`/`regulatory_drivers` populated plausibly from the sample text, no exception.

- [ ] **Step 4: One final full-pipeline check with the production generator**

Run once with the actual configured generator model (whatever `cfg['llm']['model']` is set to in `config.yaml`, e.g. `phi4-mini:3.8b-q4_K_M` on this machine) against a clause not yet generated, to confirm the full Generator → Reviewer loop still works end-to-end with the real (slow) model, not just the fast reviewer:

```bash
python pipeline.py --clause 6.2 --force
python critic.py --clause 6.2 --force
```

Expected: both complete without error (may take several minutes on `phi4-mini`); resulting `.critic.json` is valid.

- [ ] **Step 5: Manual dashboard verification (user test)**

Launch the dashboard:

```bash
python launch.py
```

Then in the browser:
1. Go to **Review** tab, select the clause reviewed in Step 2 — confirm the AI Reviewer card shows PASS/FAIL pills and a findings list (not a raw-text fallback), matching the typed-render path from Task 4.
2. If any clause in `outputs/` still has only a `.critic.md` without a `.critic.json` (a pre-migration cache, if one exists) — confirm it still renders via the legacy fallback without crashing.
3. Go to **Organization Profile**, re-run "Extract from document" on a sample org description — confirm the form populates without error.
4. Go to **Settings → AI Engine → Model Guide** (or wherever the tier table renders) — confirm the tier table still shows the same 5 tiers with the same labels/why/speed text as before this plan's changes.

Expected: all four checks pass visually; no Streamlit exceptions in the terminal running `launch.py`.

- [ ] **Step 6: Final commit (if Step 5 required any fixes)**

```bash
git add -A
git commit -m "fix: address manual verification findings from Task 14"
```

---

## Self-Review Notes

- **Spec coverage:** Phase 1 (Tasks 1-6), Phase 2 (Tasks 7-10), Phase 4 (Tasks 11-13) all covered; Phase 3 correctly has no tasks (docs-only, out of scope per user decision). Testing section's three tiers (Code/Integration/User) map to Tasks 1-13 (code), Task 14 Steps 2-4 (integration), Task 14 Step 5 (user). Both blocking security findings (base_url `/v1` construction + fail-loud, hardcoded `api_key="ollama"`) are implemented in Task 2 and explicitly re-checked for the extraction agent in Task 10.
- **Placeholder scan:** no TBD/TODO markers; every code block is complete, sourced either verbatim from the main tool's already-tested files or written new with full logic (the empty-base_url guard, the env-independent api_key test).
- **Type consistency:** `_render_reviewer_findings(verdict_obj, rev_text)` signature is consistent between Task 4's implementation and its call site update (Step 5) and its test file (Task 4, Step 2). `_build_extraction_agent()` (Task 8) is reused unchanged by Task 9. `OrgProfile`/`PersonnelEntry` field names are consistent across Task 7's schema, Task 8/9's prompts, and Task 7's field-drift test.
