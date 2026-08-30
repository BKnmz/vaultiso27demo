# Benchmark-Driven Model Catalog for Install-Time Selection

**Date:** 2026-08-30
**Status:** Approved for planning

## Why

`setup_config.py` currently maps each hardware tier (high/mid/cpu_rich/low/minimal) to
exactly one hand-picked generator model, hardcoded in `CLAUDE.md`'s Model Selection table
and (post-port) `models_catalog.json`. That table goes stale as better small models ship —
the current picks were locked in 2026-06-10. The user wants the installer to detect
hardware, then offer 2-3 ranked choices per tier, ranked by real quality signal (not just
"what someone picked six months ago"), refreshed periodically from live benchmark data.

**Dependency:** the existing `worktree-pydantic-ai-catalog-port` branch (14 commits, pushed,
unmerged as of this spec) already splits the hardcoded `TIERS` dict into
`models_catalog.json` + `_TIER_TUNING`. That branch must pass its devsecops checkpoint
(code review + security re-check + full pytest) and merge to `main` before this work starts,
since this spec extends `models_catalog.json` rather than reintroducing the static-table
structure. This is Task 1 of the implementation plan, not a separate spec.

## Scope

Demo repo (`vaultiso-demo`) only. The main tool at `C:\ClaudeData\4_ISMS_Automation\` gets
the equivalent port later, following the same manual-port pattern used for the pydantic-ai
migration (out of scope here — main tool's own catalog work isn't blocking demo's installer).

## Research Findings (2026-08-30 spike)

- **Ollama**: no benchmark API. `ollamadb.dev` (already used by the unmerged worktree's
  `refresh_catalog_best_effort()`) mirrors pull-counts/tags only — no quality scores.
- **HuggingFace Open LLM Leaderboard**: Gradio-Client API exists but is fragile — HF's own
  discussion threads report breakage, and it's a Space, not a stable REST endpoint. Rejected
  as primary signal.
- **OpenRouter**: has a dedicated `/api/v1/list-benchmarks` REST endpoint (not just
  `/models`, which is pricing/architecture only). Aggregates Artificial Analysis + Design
  Arena scores. Fields: `intelligence_index`, `coding_index`, `agentic_index`,
  `display_name`, `model_permaslug`, `pricing`, `source`. **Chosen as the benchmark
  signal** — `intelligence_index` is the closest general-quality proxy for long-form
  structured document generation (this tool's use case).
- **Gap**: OpenRouter benchmark rows key on cloud-hosted `model_permaslug`, not Ollama pull
  tags. There is no reliable automatic mapping from "OpenRouter model" to "Ollama GGUF tag."
  Fuzzy string matching was considered and rejected — false-positive risk (matching the
  wrong quantization/finetune) is unacceptable for an unattended SME installer recommending
  what to download.

## Approach: curated allowlist + periodic fetch, JSON source / MD render pair

A small hand-maintained allowlist (~15-20 entries) maps a **model family name** (e.g.
`"phi-4"`, `"qwen2.5"`, `"gemma-3"`) to its known-good Ollama pull tag(s) per size variant
(e.g. `phi4-mini:3.8b-q4_K_M`). A fetch script queries OpenRouter's `/list-benchmarks` for
`intelligence_index` on any benchmark row whose `display_name`/`model_permaslug` matches an
allowlist family, then ranks the matched Ollama-tag candidates **within** each existing
hardware tier — VRAM-fit-first stays the hard gate (a tier's candidate pool is still
"what fits this card/RAM," per the existing rule in `CLAUDE.md`); the benchmark score only
orders choices inside that already-filtered pool. It never promotes a model that doesn't fit.

Two files are written together on every refresh:
- `model_catalog.json` — machine-readable. This is what `setup_config.py` actually parses
  at install time (never parse the `.md` in production code — markdown-table parsing is
  fragile).
- `MODEL_CATALOG.md` — human-readable render of the same data, git-committed. Demo repo's
  new `CLAUDE.md` Model Selection section is replaced with a short pointer: *"See
  MODEL_CATALOG.md — auto-refreshed from OpenRouter benchmarks."* rather than embedding a
  generated table inside hand-written prose.

**Cache policy:** 90-day TTL. `install.bat` checks `model_catalog.json`'s embedded
`fetched_at` timestamp; if older than 90 days (or the file is missing), it re-fetches. A
`--refresh-catalog` flag on `setup_config.py` forces refresh regardless of age. **Any
network failure (timeout, non-200, malformed response) falls back silently to the last
cached file, or to a small built-in static fallback list if no cache exists yet — install
must never hard-fail on a benchmark-fetch problem.**

## Components

### `catalog/curated_families.json` (new)
Static, hand-maintained. Shape:
```json
{
  "families": [
    {
      "name": "phi-4",
      "openrouter_match": ["phi-4", "phi4"],
      "ollama_variants": [
        {"tag": "phi4-mini:3.8b-q4_K_M", "size_gb": 2.5, "min_ram_gb": 8, "min_vram_gb": 0}
      ]
    }
  ]
}
```
Extended by hand as new model families are worth considering. Not auto-generated.

### `catalog/refresh_model_catalog.py` (new)
1. Load `curated_families.json`.
2. `GET https://openrouter.ai/api/v1/list-benchmarks?task_type=intelligence` (no API key
   required for public benchmark data — verify during implementation; fall back to
   requiring a free OpenRouter key stored in `config.yaml` if the endpoint turns out to
   need one).
3. Match rows to allowlist families by exact `display_name`/`model_permaslug` substring
   against `openrouter_match` — no fuzzy matching.
4. For each hardware tier in `models_catalog.json`, filter matched variants to those that
   fit (existing VRAM-fit-first logic, reused not reimplemented), sort by
   `intelligence_index` descending, keep top 3.
5. Write `model_catalog.json` (adds a `benchmark_choices` array per tier alongside the
   existing default pick) and render `MODEL_CATALOG.md` from the same data.
6. On any failure at steps 2-5: leave existing `model_catalog.json`/`MODEL_CATALOG.md`
   untouched, log a warning, exit 0 (non-fatal).

### `setup_config.py` (modify)
- At install time, check cache age; call `refresh_model_catalog.py` if stale/missing/forced.
- Present 2-3 `benchmark_choices` for the detected tier (falls back to the tier's single
  existing default if `benchmark_choices` is empty/missing) with a one-line `why` each,
  let the user pick, then run `ollama pull <chosen tag>`.

### `CLAUDE.md` (new, demo repo)
Demo repo currently has no `CLAUDE.md` of its own. Create one; its Model Selection section
is the short pointer to `MODEL_CATALOG.md` described above, not an embedded table.

## Testing
- Unit tests for `refresh_model_catalog.py`: mocked OpenRouter response → correct
  family-matching, correct within-tier ranking, correct fallback-on-failure behavior
  (network error, malformed JSON, empty benchmark list).
- Unit tests for `setup_config.py`'s cache-age check and choice-presentation logic.
- No test may hit the real OpenRouter API — all HTTP calls mocked, consistent with the
  existing test suite's approach for Ollama calls (`tests/test_pipeline.py` mocks
  extensively; verified 2026-08-30).
