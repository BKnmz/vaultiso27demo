# Port pydantic-ai Migration + Model Catalog to Demo Repo

**Date:** 2026-07-27
**Status:** Approved for planning

## Why

The main tool (`C:\ClaudeData\4_ISMS_Automation\isms-automation`) has moved 5 commits past
the last sync point (`0315e95`, ported to demo as `a3bb1eb`, "v0.5.0 — adaptive skills,
PDCA layer, Risk Register"). The demo repo (`vaultiso-demo`) is missing the pydantic-ai
migration (typed Reviewer + org/personnel extraction) and the model catalog JSON split.

Main tool commits since last sync:
- `1f0d957` — auto_clauses expanded to all 23 + `item_counts` defaults (**not ported** —
  demo intentionally runs a 10-clause subset, not all 23; demo's `auto_clauses` already
  covers all 10 of its clauses)
- `2e83a27` — Phase 1/4: AI Reviewer → pydantic-ai typed agent
- `da23222` — Phase 2/4: org/personnel extraction → pydantic-ai typed agents
- `6841527` — Phase 3 docs only: rigid per-clause schemas rejected after A/B test (**not
  ported** — no code, demo has no CLAUDE.md of its own to hold the note)
- `9ec23e1` — Phase 4/4: model catalog → `models_catalog.json`

## Scope

Port Phases 1, 2, and 4 (pydantic-ai Reviewer, pydantic-ai org/personnel extraction, model
catalog split) into `vaultiso-demo`. Skip the auto_clauses expansion (Phase unrelated to
demo's subset) and Phase 3 (docs-only, no code).

## Approach: Manual phase-by-phase port

Both repos have independent git histories (separate initial commits) and demo's files
already diverged substantially from the pre-Phase-4 main tool state during the last sync
(`setup_config.py` rewritten ~521 lines, `ui/_pages/organization.py` rewritten ~393 lines
in `a3bb1eb`). A `git cherry-pick` of the three commits was considered but rejected: high
conflict risk in exactly the files Phase 4 also touches heavily. A full-tree overwrite was
also rejected: risks clobbering demo-specific config (10-clause subset, demo branding, stub
RAG excel).

Instead: copy new files as-is, hand-adapt each modified file onto demo's *current* version
(not main tool's pre-migration version), port the relevant subset of new tests, and run the
demo repo's pytest suite after each phase — mirroring how main tool itself built and
verified these phases sequentially.

## Components

### Phase 1 — Reviewer → pydantic-ai

**New files** (copied from main tool, path-identical):
- `schemas/__init__.py`
- `schemas/review.py` — `ReviewVerdict` / `FindingRow` (Literal-typed verdict, exactly 5
  findings enforced). **Verified exact shape (fact-check, 2026-07-27):**
  `FindingRow` = {dimension: Literal[5 dimension names], result: Literal["PASS","WARN","FAIL"],
  detail: str}. `ReviewVerdict` = {clause_id, clause_name, overall_assessment:
  Literal["PASS","CONDITIONAL PASS","FAIL"], confidence: Literal["HIGH","MEDIUM","LOW"],
  findings: list[FindingRow] (min_length=5, max_length=5), required_revisions,
  auditor_verdict}. Port verbatim — no field drift vs demo's needs.
- `adapters/__init__.py`
- `adapters/review_markdown.py` — `verdict_to_markdown()`, byte-compatible with the
  existing `.critic.md` shape so `pipeline.py:extract_critic_findings()` and the Review tab
  need no unrelated changes

**Modified files:**
- `critic.py` — replace raw-HTTP `call_ollama()` reviewer call with `run_reviewer_agent()`
  using `pydantic_ai.NativeOutput(ReviewVerdict)` (NOT bare `output_type=ReviewVerdict`,
  which defaults to tool-calling mode — main tool confirmed empirically that
  `qwen2.5:1.5b` exhausted output retries under tool-calling but passed first-try under
  `NativeOutput`'s grammar-constrained `json_schema` mode). `run_critic()` writes
  `.critic.md` (via adapter) + `.critic.json` sidecar. Cache-hit path prefers the JSON
  sidecar, falls back to legacy markdown regex-parse (`parse_overall_assessment`, kept as a
  compat shim) for any pre-migration cached `.critic.md` files without a sidecar.
- `ui/core.py` — add `get_review_verdict(cid)` reading the `.critic.json` sidecar.
- `ui/_pages/review.py` — `_render_reviewer_findings()` takes a typed `ReviewVerdict` first,
  falls back to the old regex table/revision parsers only when no sidecar exists (legacy
  reviews).
- `launch.py` — non-blocking Ollama version check (warn if < 0.5.0, the structured-output
  floor).
- `requirements.txt` — pin `pydantic-ai-slim[openai]==2.9.0` exact (slim + openai extra
  only — no anthropic/google provider deps as a side effect).

**Offline/no-cloud invariant (hardened after security review):**
- `config.yaml`'s `llm.base_url` is a bare host (`http://localhost:11434`, used today with
  `/api/generate`). The agent construction must explicitly build
  `f"{base_url.rstrip('/')}/v1"` in one place — do not rely on the SDK to guess it.
- **Fail loud, not silent:** if `base_url` is falsy/empty at agent-construction time, raise
  immediately. Never let the OpenAI SDK fall through to its default
  (`https://api.openai.com`) on a missing/malformed base_url.
- **Hardcode `api_key="ollama"`** (the standard pydantic-ai+Ollama dummy-key pattern) —
  never let the OpenAI SDK inherit `OPENAI_API_KEY` from the environment. This matters
  because a dev machine may have a real key set for an unrelated project; if base_url is
  ever wrong at the same time, that combination silently sends a real, billed cloud
  request. Hardcoding removes that failure mode entirely regardless of environment state.
- Port the main tool's test asserting `api.openai.com` never appears in any request, and
  add two more: a startup-time hard-fail test for empty `base_url`, and a test confirming
  `api_key` is never read from environment (assert the constructed client's key is always
  the literal `"ollama"` string, independent of `OPENAI_API_KEY` being set or unset).

### Phase 2 — Org/personnel extraction → pydantic-ai

**New file:**
- `schemas/org_profile.py` — `OrgProfile` / `PersonnelEntry` / `AssetEntry` /
  `StakeholderEntry`, field-drift-guarded 1:1 against demo's existing `ORG_JSON_SCHEMA`
  dict in `ui/core.py` (kept — still used for Settings → Organization Profile form
  rendering, not deletable).

  **Verified by fact-check agent (2026-07-27) — demo's `ORG_JSON_SCHEMA` at
  `ui/core.py:961-969` has 15 fields, exact match to main tool's `OrgProfile`:**
  scalars `name`, `industry`, `size`, `scope`; arrays `primary_processes`, `locations`,
  `departments`, `regulatory_drivers`, `legal_basis`, `critical_suppliers`,
  `existing_controls`, `certifications_existing`; nested lists `stakeholders`
  ({name, expectation} → `StakeholderEntry`), `assets` ({name, system, owner,
  classification} → `AssetEntry`), `key_personnel` ({role, name} → `PersonnelEntry`).
  No field-drift — port `schemas/org_profile.py` as-is, no adaptation needed.

**Modified files:**
- `ui/core.py` — `extract_org_with_llm()` / `extract_personnel_with_llm()` split into pure
  `_extract_*_agent_call()` (typed, testable, uses `NativeOutput`) + thin
  `st.error()`-wrapped public function. Manual `raw.find("{")...json.loads()` slicing
  deleted.

### Phase 4 — Model catalog split

**New file:**
- `models_catalog.json` — per-tier `gen_model` / `reviewer_model` / `label` / `why` /
  `speed`, append-only `legacy_tags`. Demo targets the same 5 hardware tiers as main tool
  (its `setup_config.py` runs the same hardware-detection logic) — port the full 5-tier
  catalog, not a demo-specific subset.

**Modified files:**
- `setup_config.py` — split hardcoded `TIERS` (gen_model/reviewer_model/label/why/speed
  inline) into `_TIER_TUNING` (thresholds, timeouts, `num_predict`, `item_counts` —
  install-time behavior tightly coupled to this codebase) + `models_catalog.json` (model
  identity), merged into `TIERS` at import time so every downstream reader (organization
  tab's runtime tier lookup, existing tests) sees the identical dict shape as before.
  `LEGACY_FACTORY_MODELS` derived from the catalog's `legacy_tags` array instead of a
  hardcoded Python set.

  **Verified against demo's actual current file (fact-check, 2026-07-27):** demo's
  `setup_config.py` is exactly 438 lines; lines 29-136 hold one hardcoded `TIERS` list
  covering all 5 tiers, each entry with 14 fields — `name`, `label`, `min_ram_gb`,
  `min_vram_gb`, `ollama_timeout`, `model_swap_delay`, `gen_model`, `reviewer_model`,
  `num_gpu`, `why`, `speed`, `num_predict`, `length_profile`, `item_counts`. The split must
  partition these 14 into: catalog-sourced (`gen_model`, `reviewer_model`, `label`, `why`,
  `speed` — matches main tool's `models_catalog.json` shape exactly) vs.
  `_TIER_TUNING`-retained (`min_ram_gb`, `min_vram_gb`, `ollama_timeout`,
  `model_swap_delay`, `num_gpu`, `num_predict`, `length_profile`, `item_counts`). No
  catalog-merge structure exists yet in demo — this is a from-scratch split of a currently
  fully-hardcoded file, not an adaptation of an already-partial one.

  Main tool's `models_catalog.json` (verified, 50 lines) structure to replicate:
  `{"catalog_version": "2026.07", "tiers": {<5 tier keys>: {gen_model, reviewer_model,
  label, why, speed}}, "legacy_tags": [7 model strings]}`.
- `refresh_catalog_best_effort()` — manual opt-in only (`setup_config.py
  --refresh-catalog`), never auto-invoked from `install.bat` or `main()`. Fails silently
  and safely on any error (unofficial third-party model-index API, not load-bearing).
- `.gitignore` — add `models_catalog.online_cache.json` (runtime artifact, not source).

## Testing (demo repo only, three tiers)

**Code tests** — pytest, adapted (not copied verbatim) from main tool's new tests per
phase: schema validation, adapter round-trip, critic agent/retry/`NativeOutput`, render
fallback, org extraction, catalog merge/legacy-derivation/refresh-failure. Run the full
demo pytest suite after each phase, not only at the end.

**Integration tests** — real Ollama calls end-to-end (`critic.py --clause <id> --force`,
org extraction against a sample document). Use `qwen2.5:1.5b` for these smoke checks even
where the production path uses `phi4-mini` — it's already the reviewer model, it's fast,
and it's sufficient to prove the wiring (`NativeOutput` parses, `.critic.json` written,
sidecar read back correctly). Reserve a slow `phi4-mini` run for one final full-pipeline
check, not every iteration.

**User tests** — manual, in the launched dashboard: Review tab renders a typed verdict
correctly (PASS/FAIL pills, findings table) for a freshly generated clause; Org Profile
extraction round-trips through the UI; Model Guide tab shows the catalog-sourced tier table
correctly; a pre-migration cached `.critic.md` (no sidecar) still renders via the legacy
fallback without crashing.

## Risks

- Demo's `setup_config.py` and org schema already diverged from main tool's pre-migration
  state during the `a3bb1eb` sync — both Phase 2 and Phase 4 require a direct diff against
  demo's *current* files, not an assumption of parity with main tool's history.
- Adding `pydantic-ai-slim[openai]` as a new dependency increases demo's install size;
  offline/no-cloud invariant must be re-verified on the demo side (same test as main tool:
  assert `api.openai.com` never appears in any request).
- Ollama version floor (0.5.0 for structured output) — demo's `launch.py` needs the same
  non-blocking warning; if the demo install docs recommend an older Ollama version,
  update that too.

## Out of scope

- Phase auto_clauses expansion to all 23 clauses (`1f0d957`) — demo is intentionally a
  10-clause subset.
- Phase 3 docs note (`6841527`) — no code, demo has no CLAUDE.md of its own; skipped per
  user decision.
