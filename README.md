# VaultISO27 — Demo

> **5-clause demo edition** of [VaultISO27](https://github.com/BKnmz/VaultISO27) — on-premises ISO 27001:2022 ISMS document generator.

This demo generates documents for **5 mandatory clauses** (4.1, 4.3, 5.2, 6.1, 8.2) using a stripped RAG checklist. No cloud APIs. Runs 100% locally via Ollama.

---

## Screenshots

> **To add screenshots:** take them while the tool is running, save as `.png` into `docs/screenshots/`, then commit. Suggested filenames below.

### Dashboard — progress tracker

<!-- Save as docs/screenshots/dashboard.png -->
<!-- Capture: the stepper + clause status table showing generated/approved/pending pills -->
![Dashboard](docs/screenshots/dashboard.png)

### Generate — live document generation

<!-- Save as docs/screenshots/generate.png -->
<!-- Capture: the Generate tab mid-run, showing the live log stream and progress bar -->
![Generate](docs/screenshots/generate.png)

### Review — AI Reviewer findings

<!-- Save as docs/screenshots/review.png -->
<!-- Capture: Review tab with a clause selected, showing PASS/FAIL pill task list and the Approve / Flag buttons -->
![Review](docs/screenshots/review.png)

### Documents — export centre

<!-- Save as docs/screenshots/documents.png -->
<!-- Capture: Documents tab listing all 5 generated clauses with Word download buttons visible -->
![Documents](docs/screenshots/documents.png)

### Annex A — evidence tracker

<!-- Save as docs/screenshots/annex_a.png -->
<!-- Capture: Annex A tab with a few controls filled in (applicable toggle + status + justification) -->
![Annex A](docs/screenshots/annex_a.png)

---

## Quick Start

```bat
install.bat      :: one-time setup (run from project folder, needs internet first time)
launch.bat       :: start dashboard
```

Open **http://localhost:8501** in your browser.

---

## Requirements

- Windows 10/11
- Python 3.9+
- [Ollama](https://ollama.com/) installed and running
- ~4 GB free disk space (models + dependencies)

### Models used

| Role | Model | Size |
|------|-------|------|
| Generator | `phi4-mini:3.8b-q4_K_M` | ~2.5 GB |
| AI Reviewer | `qwen2.5:1.5b` | ~1 GB |

Models are downloaded automatically by `install.bat`.

---

## Demo scope

| Clause | Document |
|--------|----------|
| 4.1 | Context of the Organization |
| 4.3 | ISMS Scope |
| 5.2 | Information Security Policy |
| 6.1 | Risk Planning |
| 8.2 | Risk Assessment |

For the full 23-clause tool, see [BKnmz/VaultISO27](https://github.com/BKnmz/VaultISO27).

---

## Workflow

```
Step 1 — Settings    Fill in your organization profile (name, sector, locations, etc.)
Step 2 — Generate    Run the pipeline; phi4-mini drafts each clause from your profile + RAG
Step 3 — Review      AI Reviewer scores each draft; approve or flag for revision
Documents            Export any clause to Word (.docx) or download all as a zip
Annex A              Track evidence for each ISO 27001:2022 control; export SoA to Excel
```

---

## Architecture

```
organization_data.json  →  Jinja2 skill template  →  phi4-mini (Ollama)
                       +  RAG context (ChromaDB)  →  .md document
                                                   →  AI Reviewer (qwen2.5)
                                                   →  Word / Excel export
```

All data stays on your machine. Zero cloud calls after first-time model download.
