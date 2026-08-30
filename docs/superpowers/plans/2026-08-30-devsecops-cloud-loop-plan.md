# Daily DevSecOps Cloud Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up two independent daily cloud routines (one per repo) that self-check repo
health each morning and only do real work — review, fix, test, PR — when something is
actually broken, never pushing to `main` unattended.

**Architecture:** Two `RemoteTrigger` cloud routines (schedule skill), each running a
self-contained Opus-orchestrated prompt. The orchestrator runs the target repo's own test
suite first as a no-op gate; only on red does it spawn Haiku-default sub-agents (reviewer,
coder, tester) via the `Agent` tool, escalating a given sub-agent to Sonnet on repeated
failure or a security-relevant finding, capped at 3 coder retries, then opens a PR via `gh`.

**Tech Stack:** Claude Code cloud routines (`RemoteTrigger` tool / `schedule` skill), `git`,
`gh` CLI (assumed present in the `anthropic_cloud` sandbox — verified in Task 1), `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-30-devsecops-cloud-loop-design.md`

## Global Constraints

- Cloud routines have no access to local files, local services (Ollama), or `rtk` — commit
  path uses plain `git`/`gh` only.
- Every fire runs the no-op gate (full pytest + static checks) first; real work only happens
  on red.
- Sub-agent model default is `haiku`; escalate to `sonnet` per-call only, never globally.
  The orchestrator itself is `claude-opus-5` and never edits code directly.
- Fix pipeline is capped at 3 coder retries; if still red, stop and report — never loop
  indefinitely.
- Commit step **never pushes directly to `main`** — always opens a PR.
- Two routines, fully independent: `BKnmz/VaultISO27` and `BKnmz/VaultISO27-demo`.

---

### Task 1: Verify cloud sandbox capabilities

**Files:** none — verification only, informs Task 2's prompt and Task 3's routine config.

**Interfaces:**
- Produces: confirmation (or a documented workaround) that later tasks depend on — if `gh`
  is unavailable, Task 2's prompt must use the GitHub REST API via `curl` instead of `gh pr
  create`.

- [ ] **Step 1: Load the RemoteTrigger tool and create one throwaway test routine**

```
ToolSearch: select:RemoteTrigger
```
Then `RemoteTrigger` with `action: "create"`, targeting a scratch repo or
`BKnmz/VaultISO27-demo` with `run_once_at` a few minutes in the future (not
`cron_expression` — this is a one-off capability probe, not the real routine), and a prompt
that simply runs:
```
Run: git --version && gh --version && python -m pytest --version
Report the output of each command, and whether `git push` to a new branch on this repo
succeeds (create branch `capability-probe`, push an empty commit, then report the result —
do not open a PR, and delete the branch afterward with `git push origin --delete
capability-probe`).
```

- [ ] **Step 2: Run it and read the log**

`RemoteTrigger action: "run"` on the probe routine, then `action: "list_runs"` →
`action: "get_run_log"` on the resulting session. Confirm: `git`/`gh`/`pytest` all present,
and the push succeeded (i.e. the routine's attached `git_repository` source has write
access — if not, this blocks Task 4's PR step and needs a GitHub token configured on the
routine before proceeding; consult the `schedule` skill's connector-setup guidance for how
to attach credentials if push fails).

- [ ] **Step 3: Record the finding, delete the probe routine**

Note in this plan's Task 2 which PR-creation method to use (`gh pr create` if available,
otherwise the GitHub REST API pattern below). Cloud routines cannot be deleted via
`RemoteTrigger` (no delete action) — direct the user to
`https://claude.ai/code/routines` to remove the probe routine manually, or leave it
disabled (`action: "update"`, `enabled: false`) if deletion isn't urgent.

---

### Task 2: Write the self-contained orchestrator prompt

**Files:**
- Create: `docs/devsecops_loop_prompt.md`

**Interfaces:**
- Produces: the exact text used as `job_config.ccr.events[].data.message.content` in both
  routines created in Task 3. Kept in the repo (not only inline in the routine config) so it
  can be reviewed and updated via a normal PR without recreating the routine each time —
  Task 3 copies its content into the `RemoteTrigger` create call verbatim, and any future
  edit updates both this file and the routine via `RemoteTrigger action: "update"`.

- [ ] **Step 1: Write the prompt**

```markdown
# DevSecOps Daily Loop — Orchestrator Instructions

You are the daily health-check orchestrator for this repository. You run once a day. You
have no memory of previous runs — everything you need to know, you determine fresh from the
repo's current state. Follow these steps in order. Do not skip the no-op gate.

## Step 1 — No-op gate

Run the full test suite and a basic static sanity check:

```
python -m pytest tests/ -q
python -c "import yaml; yaml.safe_load(open('config.yaml', encoding='utf-8'))"
```

If both succeed (pytest exits 0, the config parses with no exception): report "Daily check:
clean, no action taken" and STOP. Do not proceed to any step below. Do not open a PR. Do not
spawn any sub-agent. This is the expected outcome most days.

If either fails: proceed to Step 2.

## Step 2 — Reviewer (spawn via the Agent tool, model: haiku by default)

Spawn a sub-agent with this brief: "Run the `code-review` skill and `security-review` skill
against the current repository state (not a diff against a base branch — the working tree
as it stands). Report findings as a list: file, line, severity, one-sentence description."

If the reviewer's findings look security-relevant (anything touching auth, secrets, input
validation, or the offline/no-cloud-API invariant this project enforces) OR the reviewer's
own output suggests it struggled to reach a confident verdict, re-spawn the same review with
model: sonnet instead of trusting the haiku pass.

## Step 3 — Coder (spawn via the Agent tool, model: haiku by default)

Spawn a sub-agent with this brief: "Fix the following: [insert the pytest failure output
from Step 1, plus the reviewer's findings from Step 2]. Make the minimal change that
resolves each — do not refactor unrelated code, do not add features."

## Step 4 — Tester (spawn via the Agent tool, model: haiku)

Spawn a sub-agent to re-run `python -m pytest tests/ -q`. Report pass/fail.

- If pass: proceed to Step 5.
- If fail: this is retry N of 3. If N < 3, re-spawn the Coder (Step 3) with model: sonnet
  this time (escalate — haiku's first attempt didn't fully resolve it), including the new
  failure output. If N = 3 and still failing: STOP. Do not commit anything. Report "Daily
  check: found issues, could not resolve after 3 attempts" with the outstanding pytest
  failure output, and end here.

## Step 5 — Commit (spawn via the Agent tool, model: haiku)

Only reached if Step 4 passed. Spawn a sub-agent with this brief:

```
git checkout -b devsecops/auto-fix-<YYYY-MM-DD>
git add -A
git commit -m "fix: daily devsecops auto-fix — <one-line summary of what was wrong>"
git push -u origin devsecops/auto-fix-<YYYY-MM-DD>
gh pr create --title "DevSecOps auto-fix <YYYY-MM-DD>" --body "<summary of what Step 1 found, what Step 2's reviewer flagged, and what Step 3's coder changed>"
```

(If Task 1's capability probe found `gh` unavailable, use the GitHub REST API instead:
`curl -X POST -H "Authorization: token $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" https://api.github.com/repos/<owner>/<repo>/pulls -d '{"title":"...", "head":"devsecops/auto-fix-<date>", "base":"main", "body":"..."}'`)

**Never run `git push origin main` or any command that writes to `main` directly.** The PR
is the only output of a non-clean day. A human merges it.

## Model tiering summary (for your own reference while executing this)

- You (the orchestrator): stay on your own model throughout. Never fix code yourself —
  always delegate via the Agent tool, even for a one-line fix.
- Reviewer/Coder/Tester/Commit sub-agents: `model: haiku` by default.
- Escalate a specific sub-agent call to `model: sonnet` only when: the reviewer's findings
  are security-relevant, or a coder retry follows a failed test (Step 4's retry path).
  Escalation applies to that one call, not to every subsequent sub-agent in the run.
```

- [ ] **Step 2: Commit**

```bash
git add docs/devsecops_loop_prompt.md
git commit -m "docs: add self-contained orchestrator prompt for daily devsecops loop"
```

---

### Task 3: Create the two cloud routines

**Files:** none — routine configuration via `RemoteTrigger`, not repo code.

**Interfaces:**
- Consumes: `docs/devsecops_loop_prompt.md` (Task 2) as the routine's prompt content.

- [ ] **Step 1: Confirm the environment and repo URLs**

Use `RemoteTrigger action: "list"` first to check no routine with these names already
exists (avoid duplicates). Environment: use the `Default` environment
(`env_01FkCqis4eh2qAUNwqcFYak9`) unless the user specifies `test` instead.

- [ ] **Step 2: Create the `BKnmz/VaultISO27` routine**

```json
{
  "name": "devsecops-loop-VaultISO27",
  "cron_expression": "0 7 * * *",
  "enabled": true,
  "job_config": {
    "ccr": {
      "environment_id": "env_01FkCqis4eh2qAUNwqcFYak9",
      "session_context": {
        "model": "claude-opus-5",
        "sources": [{"git_repository": {"url": "https://github.com/BKnmz/VaultISO27"}}],
        "allowed_tools": ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Agent"]
      },
      "events": [{"data": {
        "uuid": "<fresh v4 uuid, generate at creation time>",
        "session_id": "",
        "type": "user",
        "parent_tool_use_id": null,
        "message": {"role": "user", "content": "<verbatim content of docs/devsecops_loop_prompt.md>"}
      }}]
    }
  }
}
```
`0 7 * * *` = 9am Europe/Berlin during CEST (current DST state as of 2026-08-30). Berlin
shifts to CET (UTC+1) on the last Sunday of October — after that, 9am local is `0 8 * * *`.
This is a fixed-UTC cron with no automatic DST adjustment; update the routine twice a year
via `RemoteTrigger action: "update"` with the new `cron_expression`, or accept the ~1 hour
seasonal drift if precision doesn't matter for a daily health check.

Call `RemoteTrigger` with `action: "create"` and this body. Confirm the response's routine
ID, output the link `https://claude.ai/code/routines/{ROUTINE_ID}`.

- [ ] **Step 3: Create the `BKnmz/VaultISO27-demo` routine**

Identical shape, `name: "devsecops-loop-VaultISO27-demo"`, `git_repository.url:
"https://github.com/BKnmz/VaultISO27-demo"`, a fresh UUID, everything else the same
(including the same prompt content — the prompt is repo-agnostic, it operates on "this
repository" wherever it's checked out).

- [ ] **Step 4: Record both routine IDs**

Note them in this plan file (edit this task to add the two IDs once created) so future
sessions can find them via `RemoteTrigger action: "get"` without re-listing.

---

### Task 4: Verify both failure and success paths

**Files:** none — this task deliberately introduces and reverts a throwaway failure to
prove the loop works before trusting it to run unattended.

**Interfaces:**
- Consumes: both routines from Task 3.

- [ ] **Step 1: Fire against known-green state**

`RemoteTrigger action: "run"` on `devsecops-loop-VaultISO27-demo` with the repo currently
green (confirm with a local `python -m pytest tests/ -q` first). Then `action: "list_runs"`
→ `action: "get_run_log"`. Expected: the run reports "clean, no action taken", no branch
created, no PR opened. Confirm via `gh pr list` (or the repo's PR tab) that nothing new
appeared.

- [ ] **Step 2: Introduce a deliberate, trivially-fixable failure**

On a throwaway branch (not `main`), break one test in an obvious way — e.g. change an
`assertEqual` expected value in `tests/test_setup_config.py` to something wrong — commit and
push that branch as the routine's checked-out state for this one probe (temporarily point
the routine's `git_repository.url` at that branch via `action: "update"` if the routine
config supports a branch/ref field, otherwise merge the deliberate breakage to `main`
briefly, run the probe, then revert — prefer the branch approach if the schema allows it, to
avoid ever landing a deliberately broken commit on `main`).

- [ ] **Step 3: Fire against the red state**

`RemoteTrigger action: "run"`, then inspect the log. Expected: reviewer → coder → tester
pipeline runs, the deliberate failure gets fixed, a PR opens on a `devsecops/auto-fix-*`
branch, and `main` is untouched throughout (confirm via `git log origin/main` — no new
commits landed there).

- [ ] **Step 4: Clean up**

Revert the deliberate breakage (delete the throwaway branch, or revert the temporary `main`
commit — whichever approach Step 2 used), close/merge the probe PR as appropriate, restore
the routine's `git_repository` to point at `main` if it was temporarily changed.

- [ ] **Step 5: Report to the user**

Both paths verified — routines are live and unattended-safe. Give the user both routine
links from Task 3, and the DST-adjustment note from Task 3 Step 2 as an ongoing maintenance
item.
