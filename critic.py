"""
Adversarial Critic Module
Runs a second LLM pass on generated ISMS documents, acting as a hostile ISO 27001
lead auditor. Finds gaps before the human reviewer sees the document.

Usage:
  python critic.py --clause 5.2
  python critic.py --clause 5.2 --force
  python critic.py --all               # critic every generated clause
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

import requests
import yaml

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
log = logging.getLogger("critic")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUSE_NAMES = {
    "4.1": "Context of the Organization",
    "4.2": "Interested Parties",
    "4.3": "Scope",
    "5.1": "Leadership Commitment",
    "5.2": "Information Security Policy",
    "5.3": "Roles and Responsibilities",
    "6.1": "Risk & Opportunities Framework",
    "6.1.2": "Risk Assessment Procedure",
    "6.1.3": "Risk Treatment Plan",
    "6.2": "Security Objectives",
    "7.1": "Resources",
    "7.2": "Competence",
    "7.3": "Awareness Program",
    "7.4": "Communication Plan",
    "7.5": "Documented Information",
    "8.1": "Operational Planning",
    "8.2": "Risk Assessment (Operational)",
    "8.3": "Risk Treatment (Operational)",
    "9.1": "Monitoring & Measurement",
    "9.2": "Internal Audit",
    "9.3": "Management Review",
    "10.1": "Nonconformity & Corrective Action",
    "10.2": "Continual Improvement",
}

# Clause-specific audit focus — what the critic should pay special attention to
CLAUSE_FOCUS = {
    "4.1": "internal/external issue identification, strategic alignment",
    "4.2": "all interested parties captured, communication channels defined for each",
    "4.3": "scope boundaries are unambiguous, exclusions are justified",
    "5.1": "top management commitment is explicit and actionable, not aspirational",
    "5.2": "policy contains all mandatory elements: objectives framework, commitment to requirements, commitment to improvement",
    "5.3": "segregation of duties enforced, no single person performs and approves the same action",
    "6.1": "risk appetite defined, methodology is repeatable and documented",
    "6.1.2": "all assets covered, risk owners assigned, likelihood/impact ratings justified",
    "6.1.3": "every risk from 6.1.2 has a treatment, Annex A mapping is complete, residual risks accepted",
    "6.2": "objectives are SMART and measurable, linked to policy, owner and timeline for each",
    "7.1": "resource allocation is specific, not vague",
    "7.2": "competence gaps identified and addressed, evidence of competence defined",
    "7.3": "all staff covered, new joiner process defined, effectiveness measurement included",
    "7.4": "regulatory notification timelines correct (GDPR 72h or applicable law), all stakeholders covered",
    "7.5": "retention periods defined, access controls for sensitive records specified",
    "8.1": "operational controls map to treatment plan, change management process defined",
    "8.2": "trigger events for unscheduled assessments are comprehensive",
    "8.3": "evidence of implementation specified, deviations from plan documented",
    "9.1": "metrics are measurable with named data sources, reporting frequency specified",
    "9.2": "auditor independence ensured, all clauses covered in annual programme",
    "9.3": "all mandatory ISO 27001 clause 9.3.2 inputs are addressed",
    "10.1": "root cause analysis required for all nonconformities, effectiveness verification defined",
    "10.2": "improvement linked back to monitoring results and management review outputs",
}

CRITIC_PROMPT_TEMPLATE = """You are a senior ISO 27001:2022 lead auditor performing an adversarial pre-audit review.
Your role is to find every gap, weakness, and potential nonconformity in this draft document
before it is submitted as audit evidence. Be critical and specific.

CLAUSE UNDER REVIEW: {clause_id} — {clause_name}

AUDIT CRITERIA AND REQUIREMENTS:
{rag_context}

SPECIAL FOCUS FOR THIS CLAUSE:
{clause_focus}

ORGANIZATION CONTEXT:
Name: {org_name}
Industry: {org_industry}
Size: {org_size}
Scope: {org_scope}
Legal Obligations: {legal_basis}

DOCUMENT UNDER REVIEW:
---
{document}
---

PERFORM THESE FIVE CHECKS:

1. ISO MAPPING — Does this document satisfy ALL mandatory "shall" requirements for clause {clause_id}?
   List any missing requirements explicitly.

2. COMPLETENESS — Are all required sections present and substantive?
   Flag any section that is generic filler, vague, or missing.

3. ORG SPECIFICITY — Is this genuinely specific to {org_name}, or could it apply to any company?
   Identify any generic statements that should reference the organization's actual processes/assets.

4. INTERNAL CONSISTENCY — Does anything contradict what would be expected from a coherent ISMS?
   Note any contradictions in scope, roles, or obligations.

5. AUDIT READINESS — Would an experienced ISO 27001:2022 external auditor accept this document
   as conforming evidence during a Stage 2 certification audit?

OUTPUT FORMAT — respond in this exact structure:

## Critic Review — Clause {clause_id}: {clause_name}

**Overall Assessment:** [PASS / CONDITIONAL PASS / FAIL]
**Confidence:** [HIGH / MEDIUM / LOW]

### Findings Table
| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | ISO Mapping | [PASS/FAIL/WARN] | [specific detail] |
| 2 | Completeness | [PASS/FAIL/WARN] | [specific detail] |
| 3 | Org Specificity | [PASS/FAIL/WARN] | [specific detail] |
| 4 | Internal Consistency | [PASS/FAIL/WARN] | [specific detail] |
| 5 | Audit Readiness | [PASS/FAIL/WARN] | [specific detail] |

### Required Revisions
{revision_instructions}

### Auditor Verdict
[2-3 sentences: would this pass a Stage 2 audit, what is the critical issue if any]
"""

REVISION_INSTRUCTIONS_PASS = "None — document meets requirements."
REVISION_INSTRUCTIONS_TEMPLATE = "List each revision as a bullet point with specific actionable instruction."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config(path="config.yaml"):
    import os
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if url := os.environ.get("OLLAMA_BASE_URL"):
        cfg["llm"]["base_url"] = url
    return cfg


def load_org(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def call_ollama(base_url, model, prompt, temperature=0.1, timeout=600):
    import time
    url = f"{base_url}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 1000,
        },
    }
    for attempt in range(1, 3):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except requests.exceptions.HTTPError as e:
            if attempt == 1 and getattr(e.response, "status_code", 0) == 500:
                # Ollama 500 = model swap not yet complete; wait and retry once
                log.warning("[CRITIC] Ollama 500 on attempt %d — waiting 12s for model swap, retrying...", attempt)
                time.sleep(12)
                continue
            raise RuntimeError(f"Ollama server error: {e}")
        except requests.exceptions.ReadTimeout:
            raise RuntimeError(
                f"Ollama timed out after {timeout}s (model: {model}). "
                "Model may still be loading. Wait 1-2 minutes and try again."
            )
        except requests.exceptions.ConnectionError:
            raise SystemExit(
                f"\nERROR: Cannot connect to Ollama at {base_url}\n"
                "Make sure Ollama is running: 'ollama serve'"
            )
    raise RuntimeError("Ollama failed after 2 attempts.")


def get_rag_context_for_critic(clause_id, cfg):
    """Retrieve RAG context using ChromaDB — same as pipeline."""
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        chroma_path = Path(cfg["rag"]["chroma_db_path"])
        client = chromadb.PersistentClient(path=str(chroma_path))
        collection = client.get_collection(cfg["rag"]["collection_name"])
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

        # Exact match first
        docs = []
        try:
            exact = collection.get(where={"control_id": {"$eq": clause_id}})
            if exact["documents"]:
                docs.extend(exact["documents"])
        except Exception:
            pass

        # Semantic fill
        if len(docs) < 2:
            query = f"ISO 27001 clause {clause_id} mandatory requirements shall"
            emb = model.encode([query]).tolist()
            sem = collection.query(query_embeddings=emb, n_results=3)
            for doc in sem["documents"][0]:
                if doc not in docs:
                    docs.append(doc)

        return "\n\n".join(docs[:3])
    except Exception as e:
        return f"RAG context unavailable: {e}"


def parse_overall_assessment(critic_output):
    """Extract the overall assessment from critic markdown output."""
    for line in critic_output.splitlines():
        if "**Overall Assessment:**" in line:
            if "FAIL" in line.upper():
                return "FAIL"
            elif "CONDITIONAL" in line.upper():
                return "CONDITIONAL PASS"
            elif "PASS" in line.upper():
                return "PASS"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Core critic function
# ---------------------------------------------------------------------------

def run_critic(clause_id, cfg, org, force=False):
    """
    Run adversarial critic on a generated clause document.
    Saves result to outputs/<clause_id>.critic.md
    Returns (assessment, critic_text) or (None, None) if skipped.
    """
    outputs_dir = Path(cfg["paths"]["outputs"])
    doc_file = outputs_dir / f"{clause_id}.md"
    critic_file = outputs_dir / f"{clause_id}.critic.md"

    if not doc_file.exists():
        log.warning("[SKIP] No generated document found for clause %s", clause_id)
        return None, None

    if not force and critic_file.exists():
        log.info("[CACHED] Critic review already exists for %s", clause_id)
        return parse_overall_assessment(
            critic_file.read_text(encoding="utf-8")
        ), critic_file.read_text(encoding="utf-8")

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
        document=document[:3000],  # cap to avoid context overflow on small models
        revision_instructions=REVISION_INSTRUCTIONS_TEMPLATE,
    )

    critic_model   = cfg.get("critic", {}).get("model", "qwen2.5:1.5b")
    critic_temp    = cfg.get("critic", {}).get("temperature", 0.1)
    ollama_timeout = cfg.get("timeouts", {}).get("ollama_generate", 600)

    log.info("[CRITIC] %s — %s", clause_id, clause_name)
    result = call_ollama(cfg["llm"]["base_url"], critic_model, prompt, critic_temp, timeout=ollama_timeout)
    assessment = parse_overall_assessment(result)
    log.info("[CRITIC RESULT] %s → %s", clause_id, assessment)

    critic_file.write_text(result, encoding="utf-8")
    return assessment, result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ISMS Critic — Adversarial document reviewer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--clause", help="Review a specific clause (e.g. 5.2)")
    group.add_argument("--all", action="store_true", help="Review all generated clauses")
    parser.add_argument("--force", action="store_true", help="Re-run even if critic file exists")
    args = parser.parse_args()

    cfg = load_config()

    if not cfg.get("critic", {}).get("enabled", True):
        log.warning("Critic is disabled in config.yaml. Set critic.enabled: true to enable.")
        return

    org = load_org(cfg["paths"]["inputs"])
    outputs_dir = Path(cfg["paths"]["outputs"])

    if args.clause:
        clauses = [args.clause]
    else:
        clauses = [
            cid for cid in CLAUSE_NAMES
            if (outputs_dir / f"{cid}.md").exists()
        ]

    log.info("Critic start — %d clause(s)", len(clauses))
    results = {}
    for cid in clauses:
        try:
            assessment, _ = run_critic(cid, cfg, org, force=args.force)
        except Exception as e:
            log.error("[CRITIC ERROR] %s: %s", cid, e)
            assessment = None
        if assessment:
            results[cid] = assessment

    log.info("Critic summary:")
    for cid, assessment in results.items():
        icon = {"PASS": "✓", "CONDITIONAL PASS": "~", "FAIL": "✗"}.get(assessment, "?")
        log.info("  %s %s  %s", icon, cid, assessment)


if __name__ == "__main__":
    main()
