# VaultISO27 — Demo

> **5-clause demo edition** of [VaultISO27](https://github.com/BKnmz/VaultISO27) — on-premises ISO 27001:2022 ISMS document generator.

This demo generates documents for **5 mandatory clauses** (4.1, 4.3, 5.2, 6.1, 8.2) using a stripped RAG checklist. No cloud APIs. Runs 100% locally via Ollama.

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

## Architecture

```
organization_data.json  →  Jinja2 skill template  →  phi4-mini (Ollama)
                       +  RAG context (ChromaDB)  →  .md document
                                                   →  AI Reviewer (qwen2.5)
                                                   →  Word / Excel export
```

All data stays on your machine. Zero cloud calls after first-time model download.
