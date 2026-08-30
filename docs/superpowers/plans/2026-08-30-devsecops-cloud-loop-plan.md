# Daily DevSecOps Cloud Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up two independent daily cloud routines (one per repo) that self-check repo
health each morning and only do real work — review, fix, test, PR — when something is
actually broken, never pushing to `main` unattended.

**Architecture:** Two `RemoteTrigger` cloud routines (schedule skill), each running a
self-contained Opus-orchestrated prompt. The orchestrator runs the target repo's own test
suite first as a no-op gate; only on red does it spawn Haiku-default sub-agents (reviewer,
coder, tester) via the `Agent` tool, escalating a given sub-agent to Sonnet on repeated
failure or a security-relevant finding, capped at 3 coder retries, then pushes a fix branch
(no auto-PR — see Task 1 findings below).

**Tech Stack:** Claude Code cloud routines (`RemoteTrigger` tool / `schedule` skill), `git`,
`pytest` (installed via `pip install -r requirements.txt` as the orchestrator's own first
step — not preinstalled in the sandbox, confirmed in Task 1).

**Spec:** `docs/superpowers/specs/2026-08-30-devsecops-cloud-loop-design.md`

## Status: Task 1 complete, findings changed the design (2026-08-30)

Real capability probe against `BKnmz/vaultiso27demo` (note: **actual repo name is
`vaultiso27demo`, lowercase/no hyphen** — the spec's `VaultISO27-demo` was wrong):

- `git` 2.43.0 present. `gh` CLI **not installed**. `pytest` **not preinstalled** — the
  orchestrator prompt now installs `pip install -r requirements.txt` as Step 0.
- `git push` to a new branch **failed with 403** until the user installed the Claude GitHub
  App for the repo (https://github.com/apps/claude/installations/select_target) — this is a
  one-time manual step per repo, done by the user during this session. After that, push
  succeeded cleanly.
- **Branch deletion also failed with 403**, even after push worked — the GitHub App's grant
  apparently doesn't include delete. The orchestrator never attempts to delete a branch.
- **PR-creation-via-API is unverified and was not tested** — probing for a usable token was
  blocked by Claude Code's own auto-mode safety classifier (reasonably: it pattern-matches
  credential-exfiltration attempts, even with explicit redaction instructions). User decided
  (2026-08-30): **the fix pipeline pushes a branch only, no auto-PR.** `git push`'s own
  stdout prints a "create PR" URL on success — the orchestrator captures and reports that
  link instead of calling any GitHub API. A human opens the PR manually via that link.

## Global Constraints

- Cloud routines have no access to local files, local services (Ollama), or `rtk` — commit
  path uses plain `git` only (no `gh`, no verified API token — see above).
- Every fire runs the no-op gate (full pytest + static checks) first; real work only happens
  on red.
- Sub-agent model default is `haiku`; escalate to `sonnet` per-call only, never globally.
  The orchestrator itself is `claude-opus-5` and never edits code directly.
- Fix pipeline is capped at 3 coder retries; if still red, stop and report — never loop
  indefinitely.
- Commit step **never pushes directly to `main`**, and never attempts branch deletion
  (confirmed broken in the sandbox) — pushes a fix branch and reports the PR-creation link.
- Two routines, fully independent: `BKnmz/VaultISO27` and `BKnmz/vaultiso27demo`.

---

### Task 1: Verify cloud sandbox capabilities

**Files:** none — verification only, informs Task 2's prompt and Task 3's routine config.

**Interfaces:**
- Produces: confirmation (or a documented workaround) that later tasks depend on — if `gh`
  is unavailable, Task 2's prompt must use the GitHub REST API via `curl` instead of `gh pr
  create`.

- [x] **Step 1: Load the RemoteTrigger tool and create one throwaway test routine**

Done — routine `capability-probe-vaultiso27demo` (`trig_019FmeYU5EY5QyMiuikRkWNK`), model
`claude-haiku-4-5` (a probe doesn't need Opus), targeting `BKnmz/vaultiso27demo`.

- [x] **Step 2: Run it and read the log**

Ran twice: first attempt found `git push` returning 403 ("Claude doesn't have GitHub access
... An org admin can install the Claude GitHub App"). User installed the app
(https://github.com/apps/claude/installations/select_target) mid-session; second run
confirmed push works. Full findings folded into "Status" section above.

- [x] **Step 3: Record the finding, delete the probe routine**

Findings recorded above. Cloud routines can't be deleted via `RemoteTrigger` (no delete
action, confirmed) — disabled instead (`action: "update"`, `enabled: false`). The stray
`capability-probe` branch the probe couldn't delete itself (403) was deleted from the local
checkout instead (`git push origin --delete capability-probe` — worked fine with the
session's own git credentials, unlike the sandbox's).

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

- [x] **Step 1: Write the prompt**

Written to `docs/devsecops_loop_prompt.md` (not duplicated here — see that file for the
authoritative text). Revised from this plan's original draft based on Task 1's real
findings: adds a Step 0 `pip install -r requirements.txt` (pytest isn't preinstalled),
replaces the `gh pr create`/REST-API commit step with a plain `git push` whose own stdout
"create PR" link gets captured and reported (no PR-API call — see Status section), and adds
an explicit "never attempt branch deletion" note (confirmed broken in the sandbox).

- [x] **Step 2: Commit**

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
