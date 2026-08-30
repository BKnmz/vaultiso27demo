# Daily DevSecOps Cloud Loop (Fallback Error-Fixing)

**Date:** 2026-08-30
**Status:** Approved for planning

## Why

This is a fallback safety net, not a standing requirement: the primary path is a manual
user test run of the demo (install → generate the 10 demo docs → verify quality →
screenshot on success — tracked separately, not part of this spec). If that run turns up
problems the user doesn't fix immediately, they want a daily unattended loop that catches
regressions on both `BKnmz/VaultISO27` and `BKnmz/VaultISO27-demo` going forward: reviews
code, fixes what it finds, verifies the fix, and opens a PR — without the user having to
remember to run it.

## Research Findings (2026-08-30 spike)

- **`CronCreate` (session-local tool) rejected**: jobs are session-only, gone when this
  Claude Code session ends, recurring jobs auto-expire after 7 days, and there's no way to
  pin a specific model. Not durable enough for a standing daily job.
- **Cloud routines (`schedule` skill / `RemoteTrigger`) chosen instead**, with an explicit
  tradeoff the user accepted: cloud routines cannot touch the local filesystem, local
  services, or local env vars. They only see what's pushed to the routine's `git_repository`
  source on GitHub — no access to the local Ollama server, no access to the `rtk` CLI (a
  local-machine binary per `RTK.md`), no access to the live uncommitted working tree.
  - **Commit mechanism changes accordingly**: plain `git`/`gh` inside the cloud sandbox,
    not `rtk` (rtk has no cloud equivalent and isn't installed there).
  - **Test mechanism verified compatible**: `tests/test_pipeline.py` and friends mock all
    LLM/Ollama calls extensively (24 mock/monkeypatch call sites found in
    `test_pipeline.py` alone, 2026-08-30) — the full pytest suite runs fine with zero live
    Ollama access, so the cloud sandbox can run real tests, not a stub subset.
- Minimum cloud routine interval is 1 hour (irrelevant here — daily is far above the floor).
  Recurring routines persist until manually disabled — no 7-day expiry, unlike `CronCreate`.

## Scope

Two separate cloud routines, functionally identical, targeting two different repos:
1. `BKnmz/VaultISO27` (main tool)
2. `BKnmz/VaultISO27-demo` (this repo, once pushed public per the separate marketing-site
   task)

Each routine is independent — a failure/fix cycle on one repo has no effect on the other.

## Approach

### Trigger and no-op gate
Cron fires daily (~9am Europe/Berlin, converted to UTC at creation time — confirm exact UTC
offset against DST when the routine is actually created, since Berlin shifts between
CET/CEST). Every fire, the orchestrator's **first** action is running the target repo's full
pytest suite plus a basic static/config sanity check (e.g. `config.yaml` schema, `python -c
"import <top-level modules>"`). If everything is green, it logs "clean" and exits — no
further action, no commit, no PR. This is what keeps the loop from being an infinite daily
churn machine once things are fixed: the loop only ever does real work in proportion to
what's actually broken that day, self-determined from the repo's own current state, with no
need for any cross-machine signal from the separate local test-run task.

If red, the orchestrator runs the fix pipeline below.

### Model tiering
- **Orchestrator**: the routine's own session, `model: claude-opus-5`. Orchestration only —
  routes work to sub-agents, makes the go/no-go call on each stage, never edits code or
  writes fixes itself.
- **Sub-agents (reviewer, coder, tester)**: spawned via the `Agent` tool, `model: haiku` by
  default for all three roles.
- **Escalation**: the orchestrator re-spawns a given sub-agent with `model: sonnet` only
  when the task looks like it needs deeper reasoning — e.g. the coder's haiku attempt
  doesn't fix the failing test on the first pass, or the reviewer's haiku pass flags
  something security-relevant that needs closer judgment. Escalation is per sub-agent
  call, not global — one sonnet-tier coder retry doesn't upgrade the reviewer or tester.

### Fix pipeline (only runs when the no-op gate finds red)
1. **Reviewer** (haiku, escalate to sonnet if findings look security-relevant): static
   code/config review only — no live tool execution (no rtk, no Ollama available anyway).
   Runs the `code-review` skill and `security-review` skill against the current diff/state,
   reports findings.
2. **Coder** (haiku, escalate to sonnet on repeated failure): implements fixes for whatever
   the reviewer and/or the failing pytest run surfaced.
3. **Tester** (haiku): re-runs the full pytest suite. Must be fully green before proceeding
   — if still red after a bounded number of coder retries (cap at 3, mirroring
   `pipeline.py`'s existing `max_revisions` pattern for the doc-generation revision loop),
   the orchestrator stops, leaves no PR, and reports the unresolved failure back to the user
   instead of looping indefinitely.
4. **Commit** (haiku): creates branch `devsecops/auto-fix-YYYY-MM-DD`, commits the fix,
   pushes, opens a PR via `gh pr create` targeting `main`. **Never pushes directly to
   `main`** — a human reviews and merges every auto-fix PR. (User confirmed this over the
   literal "commit" wording in the original ask, given the risk of an unattended daily bot
   landing changes on main unreviewed.)

### Verification needed during implementation (not resolved by this spec)
- Whether the cloud routine's attached `git_repository` source has push access out of the
  box, or needs a GitHub token/credential configured separately, and whether `gh` CLI is
  present in the `anthropic_cloud` environment sandbox alongside `git`. If `gh` isn't
  available, fall back to the GitHub REST API directly for PR creation.
- Whether OpenRouter's public benchmark endpoint used by the separate model-catalog spec
  needs an API key — unrelated to this spec but worth checking in the same implementation
  pass if convenient.

## Components (routine configuration, not application code)

Two `RemoteTrigger` `create` calls (one per repo), each:
```json
{
  "name": "devsecops-loop-<repo>",
  "cron_expression": "<9am Berlin in UTC, off-the-hour minute>",
  "enabled": true,
  "job_config": {
    "ccr": {
      "environment_id": "<Default environment id>",
      "session_context": {
        "model": "claude-opus-5",
        "sources": [{"git_repository": {"url": "https://github.com/BKnmz/<repo>"}}],
        "allowed_tools": ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Agent"]
      },
      "events": [{"data": {
        "uuid": "<fresh v4 uuid>",
        "session_id": "",
        "type": "user",
        "parent_tool_use_id": null,
        "message": {"role": "user", "content": "<orchestrator prompt: run pytest+static checks; if green, log clean and stop; if red, spawn reviewer/coder/tester sub-agents per the model-tiering and fix-pipeline rules in this spec, capped at 3 coder retries, then open a PR — never push main directly>"}
      }}]
    }
  }
}
```
The full orchestrator prompt text is an implementation-plan task, not written out fully
here — it must be self-contained (the cloud session starts with zero conversation context)
and needs to encode the exact no-op gate, model-tiering, retry cap, and PR-not-main rules
above.

## Testing
Cloud routines aren't unit-testable in the traditional sense. Verification is: create the
routine, use `RemoteTrigger action: "run"` to fire it once manually against a repo state
known to be green (confirm no-op, no PR opened) and then against a repo state with a
deliberately introduced, trivially-fixable failure (confirm the fix pipeline runs, tests go
green, a PR opens, and it does NOT push to main). Both checks belong in the implementation
plan as explicit tasks, not skipped.
