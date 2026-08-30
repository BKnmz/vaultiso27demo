# Benchmark-Driven Model Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the demo installer's single fixed model-per-tier with 2-3 benchmark-ranked choices, refreshed periodically from OpenRouter's public benchmark data, without ever blocking install on a network failure.

**Architecture:** A hand-curated allowlist maps model families to Ollama tags. A standalone fetch script (`refresh_model_catalog.py`) queries OpenRouter, ranks allowlisted candidates within each existing hardware tier by `intelligence_index`, and writes the result into `model_catalog.json` (machine-readable, 90-day cache) plus a rendered `MODEL_CATALOG.md`. `setup_config.py` and `install.bat` are extended to check cache age, trigger a refresh when stale, and present the ranked choices interactively at install time instead of silently picking one model.

**Tech Stack:** Python 3.9+, `requests` (already a dependency via `pip install -r requirements.txt` — verify in Task 2), `pyyaml`, `unittest` (matches existing `tests/` suite), Windows batch (`install.bat`).

**Spec:** `docs/superpowers/specs/2026-08-30-benchmark-model-catalog-design.md`

## Global Constraints

- Zero cloud API calls at **runtime** inference (unchanged project rule) — the benchmark fetch happens at **install time only**, same internet-required window as the existing pip/HuggingFace/Ollama downloads in `install.bat`.
- VRAM-fit-first stays the hard gate — benchmark score only re-ranks *within* an already hardware-filtered pool, never overrides it.
- Any network failure during the fetch (timeout, non-200, malformed JSON) must fall back silently to the last cache, or a small built-in static list if no cache exists yet — install must never hard-fail.
- No fuzzy model-name matching — only exact matches against the hand-curated allowlist.
- 90-day cache TTL, manual `--refresh-catalog` override.
- Scope is the demo repo (`vaultiso-demo`) only. The main tool port is explicitly out of scope for this plan.

---

### Task 1: Merge the pydantic-ai-catalog-port worktree

**Files:**
- Worktree: `.claude/worktrees/pydantic-ai-catalog-port` (branch `worktree-pydantic-ai-catalog-port`, already pushed, 14 commits, verified clean 2026-08-30)
- No new files — this task is a review-and-merge gate, not new code.

**Interfaces:**
- Consumes: nothing from this plan.
- Produces: `models_catalog.json` at repo root (schema: `{"catalog_version": str, "tiers": {tier_name: {gen_model, reviewer_model, label, why, speed}}, "legacy_tags": [str]}`), `setup_config.py`'s `_TIER_TUNING` + `load_models_catalog()` + `merge_tiers()`-equivalent (exact function name confirmed in Task 2, Step 1), which every later task in this plan builds on.

- [ ] **Step 1: Re-run the devsecops checkpoint on the worktree branch**

```bash
cd "C:\ClaudeData\4_ISMS_Automation\vaultiso-demo\.claude\worktrees\pydantic-ai-catalog-port"
git log --oneline main..HEAD
python -m pytest tests/ -q
```
Expected: all 14 commits listed, full test suite green. If red, fix on the worktree branch, commit, re-run until green — do not proceed to merge on a red suite.

- [ ] **Step 2: Run `/code-review` and `/security-review` against the worktree branch's diff vs `main`**

Use the `code-review` skill and `security-review` skill (both already available) against `main..worktree-pydantic-ai-catalog-port`. Fix any CONFIRMED findings on the worktree branch, re-run Step 1 after each fix.

- [ ] **Step 3: Merge to main**

```bash
cd "C:\ClaudeData\4_ISMS_Automation\vaultiso-demo"
git checkout main
git merge worktree-pydantic-ai-catalog-port --no-ff -m "$(cat <<'EOF'
feat: merge pydantic-ai migration + model catalog split

Ports the Reviewer and org/personnel extraction to pydantic-ai typed
agents, and splits the hardcoded TIERS dict into models_catalog.json +
_TIER_TUNING. Devsecops checkpoint (code review + security review +
full pytest) passed on the worktree branch before this merge.
EOF
)"
python -m pytest tests/ -q
```
Expected: clean merge (no conflicts — branch was built against a synced base per the existing spec), full suite green post-merge.

- [ ] **Step 4: Delete the now-merged worktree**

```bash
git worktree remove .claude/worktrees/pydantic-ai-catalog-port
git branch -d worktree-pydantic-ai-catalog-port
git push origin --delete worktree-pydantic-ai-catalog-port
```

---

### Task 2: Curated family allowlist

**Files:**
- Create: `catalog/curated_families.json`
- Create: `catalog/__init__.py` (empty, makes `catalog` importable)
- Create: `catalog/families.py`
- Test: `tests/test_catalog_families.py`

**Interfaces:**
- Produces: `families.py:load_curated_families(path=None) -> list[dict]`, each dict shaped `{"name": str, "openrouter_match": list[str], "ollama_variants": [{"tag": str, "size_gb": float, "min_ram_gb": int, "min_vram_gb": int}]}`.
- Consumed by: Task 3's `refresh_model_catalog.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_catalog_families.py
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from catalog.families import load_curated_families


class TestLoadCuratedFamilies(unittest.TestCase):
    def test_loads_list_of_families(self):
        families = load_curated_families()
        self.assertIsInstance(families, list)
        self.assertGreater(len(families), 0)

    def test_every_family_has_required_shape(self):
        for fam in load_curated_families():
            self.assertIn("name", fam)
            self.assertIn("openrouter_match", fam)
            self.assertIsInstance(fam["openrouter_match"], list)
            self.assertIn("ollama_variants", fam)
            self.assertGreater(len(fam["ollama_variants"]), 0)
            for variant in fam["ollama_variants"]:
                self.assertIn("tag", variant)
                self.assertIn("size_gb", variant)
                self.assertIn("min_ram_gb", variant)
                self.assertIn("min_vram_gb", variant)

    def test_known_families_present(self):
        names = {f["name"] for f in load_curated_families()}
        for expected in ("phi-4", "qwen2.5", "gemma-3", "llama-3.3", "mistral-small"):
            self.assertIn(expected, names, f"expected family '{expected}' in allowlist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_catalog_families.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'catalog'`

- [ ] **Step 3: Write `catalog/curated_families.json`**

```json
{
  "families": [
    {
      "name": "phi-4",
      "openrouter_match": ["phi-4", "phi4"],
      "ollama_variants": [
        {"tag": "phi4-mini:3.8b-q4_K_M", "size_gb": 2.5, "min_ram_gb": 8, "min_vram_gb": 0}
      ]
    },
    {
      "name": "qwen2.5",
      "openrouter_match": ["qwen2.5", "qwen-2.5"],
      "ollama_variants": [
        {"tag": "qwen2.5:1.5b", "size_gb": 0.9, "min_ram_gb": 0, "min_vram_gb": 0},
        {"tag": "qwen2.5:7b-instruct-q4_K_M", "size_gb": 4.7, "min_ram_gb": 8, "min_vram_gb": 6}
      ]
    },
    {
      "name": "gemma-3",
      "openrouter_match": ["gemma-3", "gemma3"],
      "ollama_variants": [
        {"tag": "gemma3:4b-it-qat", "size_gb": 3.3, "min_ram_gb": 8, "min_vram_gb": 4},
        {"tag": "gemma3:12b-it-qat", "size_gb": 8.9, "min_ram_gb": 0, "min_vram_gb": 12}
      ]
    },
    {
      "name": "llama-3.3",
      "openrouter_match": ["llama-3.3", "llama3.3"],
      "ollama_variants": [
        {"tag": "llama3.2:3b-q4_K_M", "size_gb": 2.0, "min_ram_gb": 8, "min_vram_gb": 0}
      ]
    },
    {
      "name": "mistral-small",
      "openrouter_match": ["mistral-small", "mistral small"],
      "ollama_variants": [
        {"tag": "mistral:7b-q4_K_M", "size_gb": 4.4, "min_ram_gb": 8, "min_vram_gb": 6}
      ]
    }
  ]
}
```
Note: this is a starting set covering the families named in the user's own research pass
(2026-08-30 web search results). Extend by hand over time — this file is never
auto-generated.

- [ ] **Step 4: Write `catalog/__init__.py` and `catalog/families.py`**

`catalog/__init__.py` — empty file.

```python
# catalog/families.py
"""Loads the hand-curated OpenRouter-family -> Ollama-tag allowlist."""
import json
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent / "curated_families.json"


def load_curated_families(path=None) -> list:
    """Return the list of curated family dicts from curated_families.json."""
    p = Path(path) if path else _DEFAULT_PATH
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data["families"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_catalog_families.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add catalog/__init__.py catalog/families.py catalog/curated_families.json tests/test_catalog_families.py
git commit -m "feat: add curated model-family allowlist for benchmark matching"
```

---

### Task 3: OpenRouter benchmark fetch + within-tier ranking

**Files:**
- Create: `catalog/openrouter_benchmarks.py`
- Test: `tests/test_openrouter_benchmarks.py`

**Interfaces:**
- Consumes: `catalog.families.load_curated_families()` (Task 2).
- Produces: `openrouter_benchmarks.py:fetch_benchmarks(session=None) -> list[dict]` (raises on failure — caller in Task 4 handles the try/except for the silent-fallback rule), `rank_candidates(families, benchmark_rows, tier_min_ram_gb, tier_min_vram_gb) -> list[dict]` returning up to 3 entries shaped `{"tag": str, "family": str, "intelligence_index": float, "size_gb": float}`, sorted descending by `intelligence_index`, filtered to variants that fit the given tier's RAM/VRAM floor.

- [ ] **Step 1: Verify the real API response shape before writing the parser**

This step is manual, not part of the test suite — run once during implementation:
```bash
curl -s "https://openrouter.ai/api/v1/list-benchmarks?task_type=intelligence" | head -c 2000
```
Confirm the top-level key holding the row array (assumed `"data"` below — a list of `{model_permaslug, display_name, intelligence_index, ...}`) and whether an `Authorization` header is required (a 401 here means it is — if so, add `openrouter_api_key` to `config.yaml`'s `catalog:` section, read via `os.environ.get("OPENROUTER_API_KEY")` as a fallback, and pass `headers={"Authorization": f"Bearer {key}"}`). If the actual field names differ from the assumption below, update Step 4's `_extract_row_score` accordingly before proceeding — do not write tests against fields that don't exist in the real response.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_openrouter_benchmarks.py
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from catalog.openrouter_benchmarks import fetch_benchmarks, rank_candidates
from catalog.families import load_curated_families


FAKE_RESPONSE = {
    "data": [
        {"model_permaslug": "microsoft/phi-4", "display_name": "Phi 4", "intelligence_index": 42.1},
        {"model_permaslug": "qwen/qwen2.5-7b-instruct", "display_name": "Qwen2.5 7B Instruct", "intelligence_index": 35.0},
        {"model_permaslug": "qwen/qwen2.5-1.5b-instruct", "display_name": "Qwen2.5 1.5B Instruct", "intelligence_index": 18.2},
        {"model_permaslug": "unrelated/some-other-model", "display_name": "Some Other Model", "intelligence_index": 99.9},
    ]
}


class TestFetchBenchmarks(unittest.TestCase):
    @patch("catalog.openrouter_benchmarks.requests.get")
    def test_fetch_returns_data_rows(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = FAKE_RESPONSE
        mock_get.return_value = mock_resp

        rows = fetch_benchmarks()
        self.assertEqual(len(rows), 4)

    @patch("catalog.openrouter_benchmarks.requests.get")
    def test_fetch_raises_on_non_200(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        with self.assertRaises(RuntimeError):
            fetch_benchmarks()

    @patch("catalog.openrouter_benchmarks.requests.get")
    def test_fetch_raises_on_timeout(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()
        with self.assertRaises(requests.exceptions.Timeout):
            fetch_benchmarks()


class TestRankCandidates(unittest.TestCase):
    def setUp(self):
        self.families = load_curated_families()

    def test_ranks_by_intelligence_index_descending(self):
        ranked = rank_candidates(self.families, FAKE_RESPONSE["data"],
                                  tier_min_ram_gb=0, tier_min_vram_gb=0)
        scores = [c["intelligence_index"] for c in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_excludes_unmatched_models(self):
        ranked = rank_candidates(self.families, FAKE_RESPONSE["data"],
                                  tier_min_ram_gb=0, tier_min_vram_gb=0)
        tags = {c["tag"] for c in ranked}
        # "unrelated/some-other-model" (99.9, highest score) must never appear -
        # it matches no curated family.
        self.assertTrue(all(t in {"phi4-mini:3.8b-q4_K_M", "qwen2.5:7b-instruct-q4_K_M",
                                   "qwen2.5:1.5b"} for t in tags))

    def test_filters_variants_that_dont_fit_tier(self):
        # minimal tier: 0 RAM/VRAM floor - only the 1.5b qwen variant qualifies
        # among the two qwen2.5 variants (7b needs 8 RAM / 6 VRAM).
        ranked = rank_candidates(self.families, FAKE_RESPONSE["data"],
                                  tier_min_ram_gb=0, tier_min_vram_gb=0)
        qwen_tags = {c["tag"] for c in ranked if c["family"] == "qwen2.5"}
        self.assertIn("qwen2.5:1.5b", qwen_tags)
        self.assertNotIn("qwen2.5:7b-instruct-q4_K_M", qwen_tags)

    def test_caps_at_three_results(self):
        many_rows = [{"model_permaslug": f"microsoft/phi-4-v{i}", "display_name": "Phi 4",
                       "intelligence_index": float(i)} for i in range(10)]
        ranked = rank_candidates(self.families, many_rows,
                                  tier_min_ram_gb=0, tier_min_vram_gb=0)
        self.assertLessEqual(len(ranked), 3)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_openrouter_benchmarks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'catalog.openrouter_benchmarks'`

- [ ] **Step 4: Write `catalog/openrouter_benchmarks.py`**

```python
"""Fetches OpenRouter benchmark scores and ranks curated-family candidates
within a hardware tier's fit. Never raises past the caller in refresh_model_catalog.py
without an explicit try/except there - see the silent-fallback rule in the spec."""
import os
import requests

_ENDPOINT = "https://openrouter.ai/api/v1/list-benchmarks"
_TIMEOUT_S = 10


def fetch_benchmarks(session=None) -> list:
    """GET the OpenRouter benchmark list. Raises RuntimeError on non-200,
    or the underlying requests exception (e.g. Timeout) on network failure -
    callers are responsible for catching and falling back."""
    getter = (session or requests).get
    headers = {}
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = getter(_ENDPOINT, params={"task_type": "intelligence"},
                   headers=headers, timeout=_TIMEOUT_S)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter benchmark fetch failed: HTTP {resp.status_code}")
    return resp.json()["data"]


def _matches_family(row: dict, family: dict) -> bool:
    haystack = f"{row.get('model_permaslug', '')} {row.get('display_name', '')}".lower()
    return any(needle.lower() in haystack for needle in family["openrouter_match"])


def rank_candidates(families: list, benchmark_rows: list,
                     tier_min_ram_gb: float, tier_min_vram_gb: float) -> list:
    """Match benchmark rows to curated families, filter variants that fit the
    given tier's RAM/VRAM floor, and return up to 3, sorted by intelligence_index
    descending."""
    candidates = []
    for family in families:
        best_score = None
        for row in benchmark_rows:
            if _matches_family(row, family):
                score = row.get("intelligence_index")
                if score is not None and (best_score is None or score > best_score):
                    best_score = score
        if best_score is None:
            continue
        for variant in family["ollama_variants"]:
            fits = variant["min_ram_gb"] <= tier_min_ram_gb or tier_min_ram_gb == 0
            fits_vram = variant["min_vram_gb"] <= tier_min_vram_gb
            # A variant fits if its own floor is at or below what this tier
            # guarantees - mirrors setup_config.py's existing gpu_ok/cpu_ok split.
            if variant["min_vram_gb"] > 0 and not fits_vram:
                continue
            if variant["min_ram_gb"] > 0 and variant["min_ram_gb"] > tier_min_ram_gb:
                continue
            candidates.append({
                "tag": variant["tag"],
                "family": family["name"],
                "intelligence_index": best_score,
                "size_gb": variant["size_gb"],
            })
    candidates.sort(key=lambda c: c["intelligence_index"], reverse=True)
    return candidates[:3]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_openrouter_benchmarks.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add catalog/openrouter_benchmarks.py tests/test_openrouter_benchmarks.py
git commit -m "feat: fetch OpenRouter benchmarks and rank candidates within tier fit"
```

---

### Task 4: `refresh_model_catalog.py` — orchestration, cache write, MD render

**Files:**
- Create: `catalog/refresh_model_catalog.py`
- Test: `tests/test_refresh_model_catalog.py`

**Interfaces:**
- Consumes: `catalog.families.load_curated_families()` (Task 2), `catalog.openrouter_benchmarks.fetch_benchmarks()` / `rank_candidates()` (Task 3), `setup_config.load_models_catalog()` / `_TIER_TUNING` (Task 1, merged).
- Produces: `refresh_model_catalog.py:refresh(force=False, catalog_path=None, md_path=None) -> bool` (returns `True` if it actually wrote new data, `False` if it left the cache untouched - either because the cache was still fresh and `force=False`, or because the fetch failed), which Task 5's `setup_config.py` calls at install time. Writes/updates `model_catalog.json`'s per-tier `benchmark_choices` key and `fetched_at` timestamp, and `MODEL_CATALOG.md`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_refresh_model_catalog.py
import sys
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from catalog.refresh_model_catalog import refresh, _is_stale


class TestIsStale(unittest.TestCase):
    def test_missing_timestamp_is_stale(self):
        self.assertTrue(_is_stale(None))

    def test_recent_timestamp_not_stale(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertFalse(_is_stale(recent))

    def test_old_timestamp_is_stale(self):
        old = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
        self.assertTrue(_is_stale(old))

    def test_boundary_89_days_not_stale(self):
        boundary = (datetime.now(timezone.utc) - timedelta(days=89)).isoformat()
        self.assertFalse(_is_stale(boundary))


class TestRefresh(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.catalog_path = self.tmpdir / "model_catalog.json"
        self.md_path = self.tmpdir / "MODEL_CATALOG.md"
        # Seed a minimal base catalog matching models_catalog.json's shape
        base = {
            "catalog_version": "2026.07",
            "tiers": {
                "minimal": {"gen_model": "qwen2.5:1.5b", "reviewer_model": "qwen2.5:1.5b",
                            "label": "Minimal (< 8 GB RAM, CPU-only)",
                            "why": "test", "speed": "test"},
            },
            "legacy_tags": ["qwen2.5:1.5b"],
        }
        self.catalog_path.write_text(json.dumps(base), encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("catalog.refresh_model_catalog.fetch_benchmarks")
    def test_writes_benchmark_choices_and_timestamp_on_success(self, mock_fetch):
        mock_fetch.return_value = [
            {"model_permaslug": "qwen/qwen2.5-1.5b-instruct", "display_name": "Qwen2.5 1.5B",
             "intelligence_index": 18.2},
        ]
        result = refresh(force=True, catalog_path=self.catalog_path, md_path=self.md_path)
        self.assertTrue(result)
        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        self.assertIn("fetched_at", data)
        self.assertIn("benchmark_choices", data["tiers"]["minimal"])
        self.assertTrue(self.md_path.exists())

    @patch("catalog.refresh_model_catalog.fetch_benchmarks")
    def test_leaves_cache_untouched_on_fetch_failure(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("network down")
        before = self.catalog_path.read_text(encoding="utf-8")
        result = refresh(force=True, catalog_path=self.catalog_path, md_path=self.md_path)
        self.assertFalse(result)
        after = self.catalog_path.read_text(encoding="utf-8")
        self.assertEqual(before, after)

    @patch("catalog.refresh_model_catalog.fetch_benchmarks")
    def test_skips_fetch_when_cache_fresh_and_not_forced(self, mock_fetch):
        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        data["fetched_at"] = datetime.now(timezone.utc).isoformat()
        self.catalog_path.write_text(json.dumps(data), encoding="utf-8")

        result = refresh(force=False, catalog_path=self.catalog_path, md_path=self.md_path)
        self.assertFalse(result)
        mock_fetch.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_refresh_model_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'catalog.refresh_model_catalog'`

- [ ] **Step 3: Write `catalog/refresh_model_catalog.py`**

```python
"""Refreshes model_catalog.json's benchmark_choices from OpenRouter, on a
90-day cache, and renders MODEL_CATALOG.md from the same data. Any failure
anywhere in the fetch/rank path leaves the existing cache untouched and
returns False - install must never hard-fail on this."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from catalog.families import load_curated_families
from catalog.openrouter_benchmarks import fetch_benchmarks, rank_candidates

_CACHE_DAYS = 90
_DEFAULT_CATALOG_PATH = Path(__file__).parent.parent / "model_catalog.json"
_DEFAULT_MD_PATH = Path(__file__).parent.parent / "MODEL_CATALOG.md"

# Mirrors setup_config.py's _TIER_TUNING RAM/VRAM floors - kept in sync by
# hand since these are install-time hardware decisions, not catalog data.
_TIER_FLOORS = {
    "high":     {"min_ram_gb": 0,  "min_vram_gb": 12},
    "mid":      {"min_ram_gb": 0,  "min_vram_gb": 6},
    "cpu_rich": {"min_ram_gb": 16, "min_vram_gb": 0},
    "low":      {"min_ram_gb": 8,  "min_vram_gb": 0},
    "minimal":  {"min_ram_gb": 0,  "min_vram_gb": 0},
}


def _is_stale(fetched_at: str) -> bool:
    if not fetched_at:
        return True
    dt = datetime.fromisoformat(fetched_at)
    return datetime.now(timezone.utc) - dt > timedelta(days=_CACHE_DAYS)


def _render_markdown(data: dict) -> str:
    lines = [
        "# Model Catalog",
        "",
        f"Auto-refreshed from OpenRouter benchmarks. Last updated: {data.get('fetched_at', 'never')}.",
        "Do not hand-edit this file - it is regenerated by `catalog/refresh_model_catalog.py`.",
        "",
    ]
    for tier_name, tier in data["tiers"].items():
        lines.append(f"## {tier['label']}")
        lines.append("")
        lines.append(f"Default: `{tier['gen_model']}` - {tier['why']}")
        choices = tier.get("benchmark_choices", [])
        if choices:
            lines.append("")
            lines.append("| Rank | Tag | Family | Intelligence Index | Size |")
            lines.append("|---|---|---|---|---|")
            for i, c in enumerate(choices, start=1):
                lines.append(f"| {i} | `{c['tag']}` | {c['family']} | "
                              f"{c['intelligence_index']:.1f} | {c['size_gb']} GB |")
        lines.append("")
    return "\n".join(lines)


def refresh(force: bool = False, catalog_path=None, md_path=None) -> bool:
    catalog_path = Path(catalog_path) if catalog_path else _DEFAULT_CATALOG_PATH
    md_path = Path(md_path) if md_path else _DEFAULT_MD_PATH

    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    if not force and not _is_stale(data.get("fetched_at")):
        return False

    try:
        families = load_curated_families()
        benchmark_rows = fetch_benchmarks()
        for tier_name, tier in data["tiers"].items():
            floor = _TIER_FLOORS.get(tier_name, {"min_ram_gb": 0, "min_vram_gb": 0})
            tier["benchmark_choices"] = rank_candidates(
                families, benchmark_rows,
                tier_min_ram_gb=floor["min_ram_gb"],
                tier_min_vram_gb=floor["min_vram_gb"],
            )
    except Exception:
        # Silent fallback per spec - leave the existing cache file untouched.
        return False

    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    md_path.write_text(_render_markdown(data), encoding="utf-8")
    return True


if __name__ == "__main__":
    import sys
    forced = "--force" in sys.argv
    changed = refresh(force=forced)
    print("Catalog refreshed." if changed else "Catalog cache still fresh - no fetch performed.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_refresh_model_catalog.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add catalog/refresh_model_catalog.py tests/test_refresh_model_catalog.py
git commit -m "feat: add refresh_model_catalog orchestration with 90-day cache + MD render"
```

---

### Task 5: Wire `setup_config.py` into the benchmark catalog

**Files:**
- Modify: `setup_config.py` (post-Task-1-merge version — uses `load_models_catalog()`/`_TIER_TUNING`, not the pre-merge hardcoded `TIERS` shown at plan-writing time)
- Modify: `tests/test_setup_config.py`

**Interfaces:**
- Consumes: `catalog.refresh_model_catalog.refresh()` (Task 4).
- Produces: `setup_config.py:choose_model_interactive(tier: dict) -> str` (returns the chosen Ollama tag), called from `install.bat` in Task 6 via a new `--choose-model` CLI mode.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_setup_config.py

class TestChooseModelInteractive(unittest.TestCase):
    def test_falls_back_to_default_when_no_benchmark_choices(self):
        tier = {"name": "minimal", "gen_model": "qwen2.5:1.5b", "benchmark_choices": []}
        with unittest.mock.patch("builtins.input", return_value=""):
            chosen = setup_config.choose_model_interactive(tier)
        self.assertEqual(chosen, "qwen2.5:1.5b")

    def test_picks_ranked_choice_by_number(self):
        tier = {
            "name": "minimal", "gen_model": "qwen2.5:1.5b",
            "benchmark_choices": [
                {"tag": "qwen2.5:1.5b", "family": "qwen2.5", "intelligence_index": 18.2, "size_gb": 0.9},
                {"tag": "phi4-mini:3.8b-q4_K_M", "family": "phi-4", "intelligence_index": 42.1, "size_gb": 2.5},
            ],
        }
        with unittest.mock.patch("builtins.input", return_value="2"):
            chosen = setup_config.choose_model_interactive(tier)
        self.assertEqual(chosen, "phi4-mini:3.8b-q4_K_M")

    def test_blank_input_picks_top_ranked_choice(self):
        tier = {
            "name": "minimal", "gen_model": "qwen2.5:1.5b",
            "benchmark_choices": [
                {"tag": "phi4-mini:3.8b-q4_K_M", "family": "phi-4", "intelligence_index": 42.1, "size_gb": 2.5},
            ],
        }
        with unittest.mock.patch("builtins.input", return_value=""):
            chosen = setup_config.choose_model_interactive(tier)
        self.assertEqual(chosen, "phi4-mini:3.8b-q4_K_M")

    def test_invalid_input_falls_back_to_top_choice(self):
        tier = {
            "name": "minimal", "gen_model": "qwen2.5:1.5b",
            "benchmark_choices": [
                {"tag": "phi4-mini:3.8b-q4_K_M", "family": "phi-4", "intelligence_index": 42.1, "size_gb": 2.5},
            ],
        }
        with unittest.mock.patch("builtins.input", return_value="not-a-number"):
            chosen = setup_config.choose_model_interactive(tier)
        self.assertEqual(chosen, "phi4-mini:3.8b-q4_K_M")
```

Add `import unittest.mock` near the top of `tests/test_setup_config.py` alongside the existing `import unittest`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_setup_config.py::TestChooseModelInteractive -v`
Expected: FAIL with `AttributeError: module 'setup_config' has no attribute 'choose_model_interactive'`

- [ ] **Step 3: Add `choose_model_interactive` and the refresh-trigger to `setup_config.py`**

Add near the bottom of `setup_config.py`, above `def main():`:

```python
def choose_model_interactive(tier: dict) -> str:
    """Present up to 3 benchmark-ranked choices for this tier and return the
    chosen Ollama tag. Falls back to the tier's single default if there are
    no benchmark_choices (fetch never ran, or ranking found nothing that fits)."""
    choices = tier.get("benchmark_choices") or []
    if not choices:
        return tier["gen_model"]

    print()
    print(f"  Ranked model choices for {tier['label']}:")
    for i, c in enumerate(choices, start=1):
        print(f"    [{i}] {c['tag']}  (family: {c['family']}, "
              f"intelligence_index: {c['intelligence_index']:.1f}, {c['size_gb']} GB)")
    print(f"  Press Enter for the top-ranked choice ([1]).")
    raw = input("  Choice: ").strip()
    if not raw:
        return choices[0]["tag"]
    try:
        idx = int(raw)
        if 1 <= idx <= len(choices):
            return choices[idx - 1]["tag"]
    except ValueError:
        pass
    print(f"  Invalid choice - using top-ranked: {choices[0]['tag']}")
    return choices[0]["tag"]
```

In `main()`, after `tier = select_tier(hw)` and before `apply_to_config(hw, tier)`, add the refresh trigger and interactive pick:

```python
    from catalog.refresh_model_catalog import refresh as refresh_catalog
    try:
        refresh_catalog(force=False)
        # Reload tier with any freshly-written benchmark_choices
        tier = select_tier(hw)
    except Exception:
        pass  # silent fallback per spec - proceed with whatever tier already has

    chosen_gen_model = choose_model_interactive(tier)
    tier = dict(tier)
    tier["gen_model"] = chosen_gen_model
```

Add a `--refresh-catalog` CLI flag (forces refresh regardless of cache age) alongside the existing `--print-models`/`--detect` flags in the `argparse` block at the bottom of the file:

```python
    parser.add_argument(
        "--refresh-catalog", action="store_true",
        help="Force a benchmark catalog refresh regardless of the 90-day cache, then exit.",
    )
    parser.add_argument(
        "--choose-model", action="store_true",
        help="Detect hardware, print ranked choices, prompt for a pick, print the chosen "
             "tag alone on stdout (for install.bat to capture). Does not write config.yaml.",
    )
```
And in the dispatch logic:
```python
    if args.refresh_catalog:
        from catalog.refresh_model_catalog import refresh as refresh_catalog
        refresh_catalog(force=True)
    elif args.choose_model:
        tier = select_tier(detect_hardware())
        print(choose_model_interactive(tier))
    elif args.print_models:
        print_models()
    elif args.detect:
        detect_main()
    else:
        main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_setup_config.py -v`
Expected: PASS (all existing + 4 new tests)

- [ ] **Step 5: Commit**

```bash
git add setup_config.py tests/test_setup_config.py
git commit -m "feat: wire interactive benchmark-ranked model choice into setup_config"
```

---

### Task 6: Interactive model pull in `install.bat`

**Files:**
- Modify: `install.bat:144-171` (the `else` branch of the Ollama-found check in STEP 5)

**Interfaces:**
- Consumes: `setup_config.py --choose-model` (Task 5) — invoked directly (not through `for /f` capture) so the interactive `input()` prompt reaches the real console; the chosen tag is captured via a **second**, non-interactive `for /f` call reading `config.yaml` back afterward.

- [ ] **Step 1: Replace the existing capture-and-pull block**

Current `install.bat:147-159` silently captures two lines from `--print-models` with no user input at all. Replace lines 147-171 with:

```bat
    :: Detect hardware, present ranked model choices, let the user pick.
    :: Run directly (not via `for /f`) so input() reaches the real console -
    :: `for /f` command substitution does not reliably pass stdin through on
    :: Windows cmd.exe.
    echo.
    python "%SCRIPT_DIR%setup_config.py"
    if errorlevel 1 (
        echo.
        echo  WARNING: Hardware detection failed. Default settings will be used.
    )

    :: Read back the chosen generator model + reviewer model from config.yaml
    :: (setup_config.py's main() already wrote them via apply_to_config).
    set "GEN_MODEL="
    set "REV_MODEL="
    for /f "delims=" %%m in ('python -c "import yaml; c=yaml.safe_load(open('%SCRIPT_DIR%config.yaml', encoding='utf-8')); print(c['llm']['model']); print(c['critic']['model'])" 2^>nul') do (
        if not defined GEN_MODEL (
            set "GEN_MODEL=%%m"
        ) else if not defined REV_MODEL (
            set "REV_MODEL=%%m"
        )
    )
    if not defined GEN_MODEL set "GEN_MODEL=phi4-mini:3.8b-q4_K_M"
    if not defined REV_MODEL set "REV_MODEL=qwen2.5:1.5b"

    echo.
    echo  Pulling document generator model  (%GEN_MODEL%)
    echo  Press Ctrl+C to skip and pull models manually later.
    echo.
    ollama pull %GEN_MODEL%
    echo.
    echo  Pulling AI reviewer model  (%REV_MODEL%)
    ollama pull %REV_MODEL%
    echo.
    echo  [OK]  AI models ready
```

Note this removes the old STEP 3b's separate call to `setup_config.py` (line 97) becoming redundant with the one now in STEP 5 — **also delete `install.bat:91-103`** (the old "STEP 3b" block) since `setup_config.py` now runs once, interactively, at STEP 5 instead of twice (silently at 3b, then again to re-read tags at 5). Renumber the `echo [STEP 4/5]` and `echo [STEP 5/5]` labels to `[STEP 3/4]` and `[STEP 4/4]` respectively (and the intro's `echo    1. ... 5. ...` list at the top of the file, lines 12-17, drops from 5 items to 4 — remove item 2's now-inaccurate wording if it referenced hardware detection as a separate step).

- [ ] **Step 2: Manual verification (batch scripts have no automated test harness in this repo)**

Run `install.bat` end-to-end on the current machine (or a throwaway venv) and confirm:
- Hardware detection prints once, not twice.
- Ranked choices are printed and the prompt accepts both a number and blank-Enter.
- `ollama pull` runs against the chosen tag, not always the tier default.
- A `Ctrl+C` at the pull prompt still exits cleanly (existing behavior, unchanged).

- [ ] **Step 3: Commit**

```bash
git add install.bat
git commit -m "feat: make install.bat present ranked model choices interactively"
```

---

### Task 7: Demo repo `CLAUDE.md` with catalog pointer

**Files:**
- Create: `CLAUDE.md` (demo repo root — confirmed absent as of 2026-08-30)

**Interfaces:**
- Consumes: nothing (a static document).
- Produces: nothing consumed by other tasks — purely documentation.

- [ ] **Step 1: Write `CLAUDE.md`**

```markdown
# VaultISO27-demo — Project Guide

## What This Is
Public demo build of VaultISO27 — on-premises ISO 27001:2022 ISMS automation. Runs a
10-clause subset (see `config.yaml:pipeline.clauses`) against local Ollama models. Zero
cloud API calls at runtime.

## Model Selection
See [`MODEL_CATALOG.md`](MODEL_CATALOG.md) — auto-refreshed from OpenRouter benchmarks
every 90 days at install time (`catalog/refresh_model_catalog.py`, triggered from
`setup_config.py`). Do not hand-edit `MODEL_CATALOG.md` or `model_catalog.json` — they are
regenerated. To force a refresh: `python setup_config.py --refresh-catalog`.

Hardware-tuning fields (VRAM/RAM thresholds, timeouts, output length per tier) live in
`setup_config.py`'s `_TIER_TUNING`, not the catalog files — those are install-time behavior
decisions coupled to this codebase, kept separate from the swappable model identity data.

## What NOT to Do
- Do not add cloud LLM clients (`anthropic`, `openai`, etc.) to runtime inference paths —
  the OpenRouter benchmark fetch in `catalog/` is install-time only and never touches
  `pipeline.py`/`critic.py`.
- Do not fuzzy-match model names when extending `catalog/curated_families.json` — exact
  substring matches only, to avoid recommending the wrong quantization to an installer.
- Do not let a catalog refresh failure block `install.bat` — it must fall back silently.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add demo repo CLAUDE.md with model catalog pointer"
```

---

### Task 8: End-to-end devsecops checkpoint

**Files:** none new — verification only.

- [ ] **Step 1: Full test suite**

Run: `python -m pytest tests/ -q`
Expected: all tests green, including the new `test_catalog_families.py`,
`test_openrouter_benchmarks.py`, `test_refresh_model_catalog.py`, and the extended
`test_setup_config.py`.

- [ ] **Step 2: Code review + security review**

Run the `code-review` skill and `security-review` skill against the full diff since Task 1's
merge commit. Pay particular attention to: the `OPENROUTER_API_KEY` handling (must never be
logged, must never be committed if a user sets one in `config.yaml`), and the `input()` call
in `choose_model_interactive` (no injection risk — it only ever indexes into a fixed list,
never `eval`s or shells out with the raw input).

- [ ] **Step 3: Fix any CONFIRMED findings, re-run Step 1, commit fixes**

- [ ] **Step 4: Manual end-to-end run**

On the current machine (documented: 20 GB RAM / 2 GB VRAM / cpu_rich tier), run
`install.bat` fresh (or `python setup_config.py` alone) and confirm the ranked choices shown
match what `MODEL_CATALOG.md` records for the `cpu_rich` tier after a `--refresh-catalog`
run.

