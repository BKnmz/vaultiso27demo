"""
ISMS Automation Pipeline
Generates ISO 27001:2022 clause documents sequentially using local Ollama + RAG.

Usage:
  python pipeline.py                      # run all clauses (skips cached)
  python pipeline.py --clause 6.1         # single clause
  python pipeline.py --clause 6.1 --force # bypass cache
  python pipeline.py --list               # show clause status
"""

import logging
import os
import re
import sys
import json
import hashlib
import argparse
from datetime import datetime
from pathlib import Path

# Force offline mode before any HuggingFace imports to prevent network
# calls to huggingface.co on model load. Without this, sentence_transformers
# tries to check for updates even when the model is cached locally, causing
# 60-120s DNS hangs when the machine is offline.
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

import yaml
import requests
from jinja2 import Template
import chromadb
from sentence_transformers import SentenceTransformer

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(_LOG_DIR / "vaultiso.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("pipeline")


# ---------------------------------------------------------------------------
# Config and helpers
# ---------------------------------------------------------------------------

def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if url := os.environ.get("OLLAMA_BASE_URL"):
        cfg["llm"]["base_url"] = url
    return cfg


def load_org_data(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def file_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def content_hash(*strings):
    h = hashlib.md5()
    for s in strings:
        h.update(s.encode("utf-8", errors="replace"))
    return h.hexdigest()


def skill_filename(clause_id):
    """Map clause ID to skill file name."""
    mapping = {
        "4.1":   "4.1_context_of_organization.md",
        "4.2":   "4.2_interested_parties.md",
        "4.3":   "4.3_scope.md",
        "5.1":   "5.1_leadership_commitment.md",
        "5.2":   "5.2_information_security_policy.md",
        "5.3":   "5.3_roles_responsibilities.md",
        "6.1":   "6.1_risk_opportunities.md",
        "6.1.2": "6.1.2_risk_assessment.md",
        "6.1.3": "6.1.3_risk_treatment.md",
        "6.2":   "6.2_security_objectives.md",
        "7.1":   "7.1_resources.md",
        "7.2":   "7.2_competence.md",
        "7.3":   "7.3_awareness.md",
        "7.4":   "7.4_communication.md",
        "7.5":   "7.5_documented_information.md",
        "8.1":   "8.1_operational_planning.md",
        "8.2":   "8.2_risk_assessment_operational.md",
        "8.3":   "8.3_risk_treatment_operational.md",
        "9.1":   "9.1_monitoring_measurement.md",
        "9.2":   "9.2_internal_audit.md",
        "9.3":   "9.3_management_review.md",
        "10.1":  "10.1_nonconformity.md",
        "10.2":  "10.2_continual_improvement.md",
    }
    return mapping.get(clause_id)


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------

def get_rag_context(collection, model, clause_id, top_k=3):
    """
    Retrieve RAG context for a clause:
    1. Exact match on control_id (gets the specific clause entry)
    2. Semantic neighbors for additional related context
    Combined and deduplicated.
    """
    query = f"ISO 27001 clause {clause_id} requirements audit criteria"
    embedding = model.encode([query]).tolist()
    docs = []

    # Step 1: exact match
    try:
        exact = collection.get(where={"control_id": {"$eq": clause_id}})
        if exact["documents"]:
            docs.extend(exact["documents"])
    except Exception as e:
        log.warning("RAG exact match failed for clause %s: %s", clause_id, e)

    # Step 2: semantic neighbors to fill remaining slots
    remaining = max(1, top_k - len(docs))
    try:
        semantic = collection.query(query_embeddings=embedding, n_results=top_k + 2)
        for doc in semantic["documents"][0]:
            if doc not in docs:
                docs.append(doc)
                if len(docs) >= top_k:
                    break
    except Exception as e:
        log.warning("RAG semantic search failed: %s", e)

    if docs:
        return "\n\n".join(docs[:top_k])
    return f"ISO 27001:2022 Clause {clause_id} — no specific checklist entry found."


# ---------------------------------------------------------------------------
# Upstream context
# ---------------------------------------------------------------------------

# Which prior clauses are most relevant as upstream context for each clause
UPSTREAM_MAP = {
    "4.2":   ["4.1"],
    "4.3":   ["4.1", "4.2"],
    "5.1":   ["4.1", "4.3"],
    "5.2":   ["4.1", "4.2", "4.3"],
    "5.3":   ["5.1", "5.2"],
    "6.1":   ["4.1", "4.2", "4.3"],
    "6.1.2": ["6.1", "4.3"],
    "6.1.3": ["6.1.2", "6.1"],
    "6.2":   ["5.2", "6.1"],
    "7.1":   ["6.2", "5.3"],
    "7.2":   ["5.3", "7.1"],
    "7.3":   ["5.2", "7.2"],
    "7.4":   ["4.2", "5.3"],
    "7.5":   ["5.2", "7.1"],
    "8.1":   ["6.1.3", "6.2"],
    "8.2":   ["6.1.2", "6.1"],
    "8.3":   ["6.1.3", "8.2"],
    "9.1":   ["6.2", "8.1"],
    "9.2":   ["9.1", "5.3"],
    "9.3":   ["9.1", "9.2", "6.2"],
    "10.1":  ["9.2", "9.3"],
    "10.2":  ["10.1", "9.3", "9.1"],
}

MAX_UPSTREAM_CHARS = 300  # max chars per upstream clause snippet


def build_upstream_context(clause_id, outputs_dir):
    """Collect truncated summaries from previously generated upstream clauses."""
    upstream_ids = UPSTREAM_MAP.get(clause_id, [])
    snippets = []
    for uid in upstream_ids:
        out_file = outputs_dir / f"{uid}.md"
        if out_file.exists():
            text = out_file.read_text(encoding="utf-8", errors="replace")
            # Take first MAX_UPSTREAM_CHARS chars as a summary signal
            snippet = text[:MAX_UPSTREAM_CHARS].replace("\n", " ").strip()
            snippets.append(f"[Clause {uid}]: {snippet}...")
    return "\n".join(snippets) if snippets else "No upstream context available yet."


# ---------------------------------------------------------------------------
# Ollama call
# ---------------------------------------------------------------------------

def call_ollama(base_url, model_name, prompt, temperature=0.2, timeout=600):
    """Send prompt to Ollama and return generated text."""
    url = f"{base_url}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 1200,
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        if not text or len(text.split()) < 20:
            raise RuntimeError(
                f"Ollama returned empty/short response for model '{model_name}'. "
                f"Ensure model is pulled and has enough context. Raw: {resp.text[:300]}"
            )
        return text
    except requests.exceptions.ReadTimeout:
        raise RuntimeError(
            f"\nERROR: Ollama timed out after {timeout}s (model: {model_name}).\n"
            "Model may still be loading (cold start) or system under load.\n"
            "Wait 1-2 minutes and try again."
        )
    except requests.exceptions.ConnectionError:
        raise SystemExit(
            f"\nERROR: Cannot connect to Ollama at {base_url}\n"
            "Make sure Ollama is running: 'ollama serve'\n"
            f"And the model is pulled: 'ollama pull {model_name}'"
        )


# ---------------------------------------------------------------------------
# Revision loop helpers
# ---------------------------------------------------------------------------

SKILL_STYLE_PREAMBLE = """\
WRITING STYLE — apply strictly to all output:
- Formal third-person declarative ("The organization shall…" / "{org_name} maintains…")
- No first-person plural: replace "our", "we", "us" with the organization name or "the organization"
- No filler words: do not use "simply", "just", "really", "very", "basically"
- Auditor-facing tone: factual, unambiguous, defensible
- Use ISO 27001:2022 terminology exactly as written in the standard

"""

REVISION_PROMPT = """\
You are an ISO 27001:2022 compliance specialist revising a draft ISMS document based on auditor feedback.

CLAUSE: {clause_id} — {clause_name}
ORGANIZATION: {org_name} | {org_size} | {org_industry}
{user_notes_block}
AUDITOR FINDINGS THAT MUST BE FIXED:
{critic_findings}

CURRENT DRAFT:
{document}

TASK: Produce a revised version of the document that addresses every auditor finding above.
- Keep sections that already meet requirements — do not remove compliant content.
- Be specific to {org_name}. Do not add generic filler.
- Do not invent requirements not already in the draft.
- Formal third-person only. No "our", "we", "us".

OUTPUT FORMAT: Markdown with numbered section headers matching the original structure.

CRITICAL: Output ONLY the revised document body. Do NOT include:
- A "Changes Made", "Revisions", "Auditor Findings", or "Changelog" section
- Word counts or meta-commentary (e.g. "(Word Count: ~350)")
- References to "the auditor" or "the reviewer" in the document body
- Any preamble such as "Here is the revised document:"
"""

USER_REVISION_PROMPT = """\
You are an ISO 27001:2022 compliance specialist revising a draft ISMS document based on human reviewer instructions.

CLAUSE: {clause_id} — {clause_name}
ORGANIZATION: {org_name} | {org_size} | {org_industry}

HUMAN REVIEWER INSTRUCTIONS (authoritative — address all points):
{user_notes}

CURRENT DRAFT:
{document}

TASK: Produce a revised version that fully addresses the reviewer's instructions above.
- Keep sections not mentioned by the reviewer — do not remove content unnecessarily.
- Be specific to {org_name}. Do not add generic filler.
- Do not invent requirements not already in the draft.
- Formal third-person only. No "our", "we", "us".

OUTPUT FORMAT: Markdown with numbered section headers matching the original structure.

CRITICAL: Output ONLY the revised document body. Do NOT include:
- A "Changes Made", "Revisions", "Auditor Findings", or "Changelog" section
- Word counts or meta-commentary (e.g. "(Word Count: ~350)")
- References to "the reviewer" in the document body
- Any preamble such as "Here is the revised document:"
"""

CLAUSE_NAMES_PIPELINE = {
    "4.1": "Context of the Organization", "4.2": "Interested Parties",
    "4.3": "Scope", "5.1": "Leadership Commitment",
    "5.2": "Information Security Policy", "5.3": "Roles and Responsibilities",
    "6.1": "Risk & Opportunities Framework", "6.1.2": "Risk Assessment Procedure",
    "6.1.3": "Risk Treatment Plan", "6.2": "Security Objectives",
    "7.1": "Resources", "7.2": "Competence", "7.3": "Awareness Program",
    "7.4": "Communication Plan", "7.5": "Documented Information",
    "8.1": "Operational Planning", "8.2": "Risk Assessment (Operational)",
    "8.3": "Risk Treatment (Operational)", "9.1": "Monitoring & Measurement",
    "9.2": "Internal Audit", "9.3": "Management Review",
    "10.1": "Nonconformity & Corrective Action", "10.2": "Continual Improvement",
}


def extract_critic_findings(critic_text):
    """Extract actionable findings from critic output (table + revisions + verdict)."""
    lines = critic_text.splitlines()
    findings = []
    in_section = False
    for line in lines:
        if "### Findings Table" in line or "### Required Revisions" in line:
            in_section = True
        if in_section:
            findings.append(line)
    return "\n".join(findings).strip() if findings else critic_text[:1500]


def run_revision_loop(clause_id, cfg, org, out_file, max_revisions):
    """
    Generator → Reviewer → auto-correct loop.

    Runs up to max_revisions critic attempts. Early-exits on PASS.
    On FAIL or CONDITIONAL PASS, re-drafts with critic feedback and loops.

    Each critic attempt is snapshotted to `outputs/<clause_id>.critic.attempt-N.md`
    so the user can audit the back-and-forth. Final outcome (assessment + attempts)
    is recorded in `outputs/<clause_id>.revision.json`.

    Returns final assessment string ("PASS" / "CONDITIONAL PASS" / "FAIL" / None).
    """
    from critic import run_critic, parse_overall_assessment

    clause_name = CLAUSE_NAMES_PIPELINE.get(clause_id, clause_id)
    outputs_dir = out_file.parent
    history = []

    assessment = None
    for attempt in range(1, max_revisions + 1):
        assessment, critic_text = run_critic(clause_id, cfg, org, force=True)

        if assessment is None:
            return None

        # Snapshot critic output for this attempt
        snap = outputs_dir / f"{clause_id}.critic.attempt-{attempt}.md"
        try:
            snap.write_text(critic_text, encoding="utf-8")
        except Exception as e:
            log.warning("[REVISION] %s — could not write attempt snapshot: %s", clause_id, e)

        history.append({"attempt": attempt, "assessment": assessment})

        if assessment == "PASS":
            log.info("[REVISION] %s — PASS on attempt %d/%d", clause_id, attempt, max_revisions)
            _write_revision_meta(outputs_dir, clause_id, assessment, history)
            return assessment

        if attempt == max_revisions:
            log.info(
                "[REVISION] %s — %s after %d attempt(s), keeping best draft",
                clause_id, assessment, max_revisions,
            )
            _write_revision_meta(outputs_dir, clause_id, assessment, history)
            return assessment

        verdict_label = "FAIL" if assessment == "FAIL" else "CONDITIONAL PASS"
        log.info(
            "[REVISION] %s — %s, auto-correcting (attempt %d/%d)",
            clause_id, verdict_label, attempt, max_revisions,
        )

        findings = extract_critic_findings(critic_text)
        document = out_file.read_text(encoding="utf-8", errors="replace")

        revision_prompt = REVISION_PROMPT.format(
            clause_id=clause_id,
            clause_name=clause_name,
            org_name=org.get("name", ""),
            org_size=org.get("size", ""),
            org_industry=org.get("industry", ""),
            user_notes_block="",
            critic_findings=findings,
            document=document[:6000],
        )

        revised = call_ollama(
            cfg["llm"]["base_url"],
            cfg["llm"]["model"],
            revision_prompt,
            cfg["llm"]["temperature"],
            timeout=cfg.get("timeouts", {}).get("ollama_generate", 600),
        )
        out_file.write_text(revised, encoding="utf-8")

    _write_revision_meta(outputs_dir, clause_id, assessment, history)
    return assessment


def _write_revision_meta(outputs_dir, clause_id, final_assessment, history):
    """Persist the revision-loop outcome so the UI can surface it."""
    meta = {
        "clause_id": clause_id,
        "final_assessment": final_assessment,
        "attempts": history,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    try:
        (outputs_dir / f"{clause_id}.revision.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log.warning("[REVISION] %s — could not write revision meta: %s", clause_id, e)


def regenerate_with_user_notes(clause_id, cfg, org):
    """
    Re-generate a clause document using the human reviewer's notes stored in
    outputs/{clause_id}.status.json. Overwrites the current draft, appends a
    version snapshot, then re-runs the AI Reviewer if the clause is in auto_clauses.

    Returns (success: bool, message: str).
    """
    outputs_dir = Path(cfg["paths"]["outputs"])
    out_file = outputs_dir / f"{clause_id}.md"
    status_file = outputs_dir / f"{clause_id}.status.json"
    clause_name = CLAUSE_NAMES_PIPELINE.get(clause_id, clause_id)

    if not status_file.exists():
        return False, "No status file found — flag the document for revision first."

    try:
        status_data = json.loads(status_file.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"Could not read status file: {e}"

    user_notes = status_data.get("notes", "").strip()
    if not user_notes:
        return False, "No reviewer notes found. Add notes in the Decision notes box and flag the document first."

    if not out_file.exists():
        return False, f"No generated document found for {clause_id}."

    document = out_file.read_text(encoding="utf-8", errors="replace")

    revision_prompt = USER_REVISION_PROMPT.format(
        clause_id=clause_id,
        clause_name=clause_name,
        org_name=org.get("name", ""),
        org_size=org.get("size", ""),
        org_industry=org.get("industry", ""),
        user_notes=user_notes,
        document=document[:6000],
    )

    log.info("[USER-REGEN] %s — regenerating with reviewer notes", clause_id)
    revised = call_ollama(
        cfg["llm"]["base_url"],
        cfg["llm"]["model"],
        revision_prompt,
        cfg["llm"]["temperature"],
        timeout=cfg.get("timeouts", {}).get("ollama_generate", 600),
    )

    if not revised or not revised.strip():
        return False, "Generator returned empty response. Check Ollama is running."

    revised = _clean_generated_markdown(revised)
    out_file.write_text(revised, encoding="utf-8")
    _write_version(out_file, revised, cfg, event="user_regen")

    hash_file = outputs_dir / f"{clause_id}.hash"
    if hash_file.exists():
        hash_file.unlink()

    from core import save_status
    save_status(clause_id, "PENDING", "")

    auto_clauses = cfg.get("critic", {}).get("auto_clauses", [])
    if cfg.get("critic", {}).get("enabled") and clause_id in auto_clauses:
        log.info("[USER-REGEN] %s — running AI Reviewer on revised draft", clause_id)
        run_revision_loop(clause_id, cfg, org, out_file, max_revisions=1)

    log.info("[USER-REGEN] %s — done", clause_id)
    return True, "Document regenerated using your reviewer notes."


# ---------------------------------------------------------------------------
# Markdown post-processor
# ---------------------------------------------------------------------------

def _clean_generated_markdown(text: str) -> str:
    """Strip common LLM artefacts from generated/revised ISMS documents."""
    if not text:
        return text
    # Strip wrapping code fences (```markdown ... ``` or ``` ... ```)
    text = re.sub(r"^```[a-zA-Z]*\s*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*$", "", text, flags=re.MULTILINE)
    # Strip trailing (Word Count: ~NNN) meta lines
    text = re.sub(r"\(Word Count:[^)]*\)\s*$", "", text, flags=re.MULTILINE)
    # Strip trailing Auditor Findings / Revisions / Changelog sections
    text = re.sub(
        r"\n##+\s*(Auditor Findings|Revisions|Changes Made|Change Log|Changelog)[^\n]*.*$",
        "", text, flags=re.DOTALL | re.IGNORECASE,
    )
    return text.strip()


# ---------------------------------------------------------------------------
# Version history
# ---------------------------------------------------------------------------

def _write_version(out_file, content, cfg, event="generation", note=""):
    """Append a version snapshot to {clause}.versions.json, capping at configured limit."""
    vers_file = out_file.with_suffix(".versions.json")
    max_v = cfg.get("export", {}).get("version_history_cap", 5)
    versions = []
    if vers_file.exists():
        try:
            versions = json.loads(vers_file.read_text(encoding="utf-8"))
        except Exception:
            versions = []
    entry = {
        "version": len(versions) + 1,
        "timestamp": datetime.now().isoformat(),
        "content": content,
        "event": event,
    }
    if note:
        entry["note"] = note
    versions.append(entry)
    if len(versions) > max_v:
        versions = versions[-max_v:]
    vers_file.write_text(json.dumps(versions, indent=2, ensure_ascii=False), encoding="utf-8")


def write_review_note_event(clause_id, notes, cfg):
    """Write a version snapshot when user flags a clause with notes (no regeneration)."""
    outputs_dir = Path(cfg["paths"]["outputs"])
    out_file = outputs_dir / f"{clause_id}.md"
    if not out_file.exists():
        return
    try:
        content = out_file.read_text(encoding="utf-8", errors="replace")
        _write_version(out_file, content, cfg, event="review_note", note=notes)
        log.info("[REVIEW-NOTE] %s — version snapshot written", clause_id)
    except Exception as e:
        log.warning("[REVIEW-NOTE] %s — could not write version snapshot: %s", clause_id, e)


# ---------------------------------------------------------------------------
# Single clause generation
# ---------------------------------------------------------------------------

def generate_clause(clause_id, cfg, org, collection, embed_model, force=False):
    outputs_dir = Path(cfg["paths"]["outputs"])
    skills_dir = Path(cfg["paths"]["skills"])
    outputs_dir.mkdir(exist_ok=True)

    out_file = outputs_dir / f"{clause_id}.md"
    hash_file = outputs_dir / f"{clause_id}.hash"

    # Load skill template
    fname = skill_filename(clause_id)
    if not fname:
        log.warning("[SKIP] No skill file mapped for clause %s", clause_id)
        return False
    skill_path = skills_dir / fname
    if not skill_path.exists():
        log.warning("[SKIP] Skill file not found: %s", skill_path)
        return False
    skill_text = skill_path.read_text(encoding="utf-8")

    # Check cache
    rag_context = get_rag_context(collection, embed_model, clause_id, cfg["rag"]["top_k"])
    upstream_context = build_upstream_context(clause_id, outputs_dir)
    current_hash = content_hash(
        json.dumps(org, sort_keys=True),
        rag_context,
        skill_text,
    )

    if not force and out_file.exists() and hash_file.exists():
        if hash_file.read_text().strip() == current_hash:
            log.info("[CACHED] %s", clause_id)
            return True

    # Normalise org assets to simple strings so skill templates can join() them
    org_render = dict(org)
    raw_assets = org.get("assets", [])
    org_render["assets"] = [
        (a.get("name") or a.get("system") or str(a))
        + (f" [{a['type']}]" if a.get("type") else "")
        + (f" — {a['data_classification']}" if a.get("data_classification") else
           f" — {a['classification']}" if a.get("classification") else "")
        + (f" (owner: {a['responsible']})" if a.get("responsible") else
           f" (owner: {a['owner']})" if a.get("owner") else "")
        + (f" risk={a['risk_score']}" if a.get("risk_score") else "")
        if isinstance(a, dict) else str(a)
        for a in raw_assets
    ]

    # Render prompt (prepend style preamble so LLM adopts formal ISO tone)
    template = Template(skill_text)
    prompt = SKILL_STYLE_PREAMBLE + template.render(
        clause_id=clause_id,
        org=org_render,
        rag_context=rag_context,
        upstream_context=upstream_context,
    )

    # Call LLM
    log.info("[GENERATING] %s — %s", clause_id, fname)
    result = call_ollama(
        cfg["llm"]["base_url"],
        cfg["llm"]["model"],
        prompt,
        cfg["llm"]["temperature"],
        timeout=cfg.get("timeouts", {}).get("ollama_generate", 600),
    )
    result = _clean_generated_markdown(result)
    log.info("[DONE] %s — %d words", clause_id, len(result.split()))

    # Save output and hash
    out_file.write_text(result, encoding="utf-8")
    hash_file.write_text(current_hash)
    _write_version(out_file, result, cfg)

    # Auto-run critic + revision loop for flagged clauses
    auto_clauses = cfg.get("critic", {}).get("auto_clauses", [])
    critic_enabled = cfg.get("critic", {}).get("enabled", False)
    if critic_enabled and clause_id in auto_clauses:
        try:
            import time
            swap_delay = cfg.get("timeouts", {}).get("model_swap_delay", 12)
            log.info("[Auto-review] Waiting %ds for model swap (generator → reviewer)...", swap_delay)
            time.sleep(swap_delay)
            max_revisions = cfg.get("critic", {}).get("max_revisions", 2)
            run_revision_loop(clause_id, cfg, org, out_file, max_revisions)
        except Exception as e:
            log.error("[CRITIC ERROR] %s: %s", clause_id, e)

    return True


# ---------------------------------------------------------------------------
# Status listing
# ---------------------------------------------------------------------------

def list_status(cfg):
    outputs_dir = Path(cfg["paths"]["outputs"])
    clauses = cfg["pipeline"]["clauses"]
    print(f"\nISMS Clause Status ({len(clauses)} clauses)\n" + "-" * 40)
    for clause_id in clauses:
        out_file = outputs_dir / f"{clause_id}.md"
        status_file = outputs_dir / f"{clause_id}.status.json"
        if not out_file.exists():
            status = "MISSING"
        elif status_file.exists():
            s = json.loads(status_file.read_text())
            status = s.get("status", "draft").upper()
        else:
            status = "DRAFT"
        icon = {"MISSING": "✗", "DRAFT": "~", "APPROVED": "✓", "REVISION": "!"}.get(status, "?")
        print(f"  {icon} {clause_id:<8} {status}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ISMS Automation Pipeline")
    parser.add_argument("--clause", help="Generate a single clause (e.g. 6.1)")
    parser.add_argument("--force", action="store_true", help="Bypass output cache")
    parser.add_argument("--list", action="store_true", help="Show clause status and exit")
    args = parser.parse_args()

    cfg = load_config()
    org = load_org_data(cfg["paths"]["inputs"])

    if args.list:
        list_status(cfg)
        return

    # Init ChromaDB
    chroma_path = Path(cfg["rag"]["chroma_db_path"])
    if not chroma_path.exists():
        raise SystemExit(
            "ERROR: ChromaDB index not found. Run 'python rag_setup.py' first."
        )
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_collection(cfg["rag"]["collection_name"])

    # Load embedding model (same as rag_setup.py)
    print("Loading embedding model...")
    embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    clauses = [args.clause] if args.clause else cfg["pipeline"]["clauses"]

    log.info("Pipeline start — %d clause(s)", len(clauses))
    success = 0
    for clause_id in clauses:
        ok = generate_clause(clause_id, cfg, org, collection, embed_model, force=args.force)
        if ok:
            success += 1

    log.info("Pipeline done — %d/%d clauses processed. Outputs: %s",
             success, len(clauses), Path(cfg["paths"]["outputs"]).resolve())


if __name__ == "__main__":
    main()
