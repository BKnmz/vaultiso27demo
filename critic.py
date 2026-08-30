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
import time
from pathlib import Path

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

import yaml

from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from adapters.review_markdown import verdict_to_markdown
from schemas.review import ReviewVerdict

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

VERDICT RULES — decide the Overall Assessment using exactly these rules:
- FAIL — one or more of the five checks is FAIL (a mandatory "shall" requirement is missing,
  or the document could not stand as audit evidence).
- CONDITIONAL PASS — no check is FAIL, but one or more is WARN (the document is broadly
  conformant but needs specific minor fixes before a Stage 2 audit).
- PASS — all five checks are PASS (no mandatory gaps, audit-ready as written).
Do NOT default to FAIL. Only choose FAIL when you can name the specific failed check above.

OUTPUT FORMAT — respond in this exact structure. Replace every [bracketed placeholder] with
your own finding; never output the brackets themselves:

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


def run_reviewer_agent(base_url, model, prompt, temperature=0.1, timeout=600):
    """
    Call the AI Reviewer via pydantic-ai, pointed at local Ollama's OpenAI-compatible
    endpoint (never a real cloud API — base_url always resolves to config's llm.base_url).

    Uses NativeOutput to force Ollama's grammar-constrained decoding (format=json_schema)
    rather than pydantic-ai's default tool-calling structured-output mode — confirmed
    empirically that qwen2.5:1.5b exhausts its output retries under tool-calling mode but
    succeeds first-try under NativeOutput, since the schema constraint is enforced at the
    token level regardless of the model's tool-calling reliability.

    api_key is always the hardcoded literal "ollama" — never read from OPENAI_API_KEY or
    any environment variable, so a real key set on the dev machine for an unrelated project
    can never combine with a misconfigured base_url to send a real, billed cloud request.

    Returns a ReviewVerdict. Raises ValueError if base_url is empty (fail loud rather than
    let the OpenAI SDK silently fall back to https://api.openai.com). Raises SystemExit on
    connection failure, RuntimeError on a persistent server error.
    """
    if not base_url:
        raise ValueError(
            "run_reviewer_agent: base_url is empty — refusing to let the OpenAI SDK "
            "fall back to its default (https://api.openai.com)."
        )
    provider = OpenAIProvider(base_url=f"{base_url}/v1", api_key="ollama")
    pyd_model = OpenAIChatModel(
        model,
        provider=provider,
        settings=ModelSettings(temperature=temperature, timeout=timeout),
    )
    agent = Agent(pyd_model, output_type=NativeOutput(ReviewVerdict))

    for attempt in range(1, 3):
        try:
            result = agent.run_sync(prompt)
            return result.output
        except ModelHTTPError as e:
            if attempt == 1 and e.status_code == 500:
                # Ollama 500 = model swap not yet complete; wait and retry once
                log.warning("[CRITIC] Ollama 500 on attempt %d — waiting 12s for model swap, retrying...", attempt)
                time.sleep(12)
                continue
            raise RuntimeError(f"Ollama server error: {e}")
        except ModelAPIError as e:
            raise SystemExit(
                f"\nERROR: Cannot connect to Ollama at {base_url}\n"
                "Make sure Ollama is running: 'ollama serve'"
            ) from e
        except UnexpectedModelBehavior as e:
            # Model emitted syntactically valid but schema-invalid output (e.g. a
            # duplicated ReviewVerdict dimension) and exhausted pydantic-ai's own
            # output-retries. Not a ModelHTTPError/ModelAPIError sibling - convert
            # to RuntimeError so every caller's existing except RuntimeError path
            # (pipeline.py, ui/_pages/review.py) handles it the same as a server error.
            raise RuntimeError(f"AI Reviewer returned invalid output: {e}") from e
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
    """Extract the overall assessment from critic markdown output.

    Legacy-format shim: only used as a fallback when reading a cached .critic.md
    written before the pydantic-ai migration (no .critic.json sidecar present).
    """
    for line in critic_output.splitlines():
        if "**Overall Assessment:**" in line:
            # Model echoed the literal placeholder instead of deciding — surface as a
            # visible UNKNOWN rather than silently scoring FAIL on the bracketed example.
            if "[" in line:
                return "UNKNOWN"
            upper = line.upper()
            # CONDITIONAL must be checked before FAIL: "CONDITIONAL PASS" contains neither
            # but a careless FAIL-first check would mis-route a line mentioning both words.
            if "CONDITIONAL" in upper:
                return "CONDITIONAL PASS"
            elif "FAIL" in upper:
                return "FAIL"
            elif "PASS" in upper:
                return "PASS"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Core critic function
# ---------------------------------------------------------------------------

def run_critic(clause_id, cfg, org, force=False):
    """
    Run adversarial critic on a generated clause document.
    Saves result to outputs/<clause_id>.critic.md and outputs/<clause_id>.critic.json
    Returns (assessment, critic_text) or (None, None) if skipped.
    """
    outputs_dir = Path(cfg["paths"]["outputs"])
    doc_file = outputs_dir / f"{clause_id}.md"
    critic_file = outputs_dir / f"{clause_id}.critic.md"
    critic_json_file = outputs_dir / f"{clause_id}.critic.json"

    if not doc_file.exists():
        log.warning("[SKIP] No generated document found for clause %s", clause_id)
        return None, None

    if not force and critic_file.exists():
        log.info("[CACHED] Critic review already exists for %s", clause_id)
        cached_md = critic_file.read_text(encoding="utf-8")
        if critic_json_file.exists():
            try:
                cached_verdict = ReviewVerdict.model_validate_json(
                    critic_json_file.read_text(encoding="utf-8")
                )
                return cached_verdict.overall_assessment, cached_md
            except Exception:
                pass  # fall through to legacy markdown parse
        return parse_overall_assessment(cached_md), cached_md

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
        document=document[:5000],  # cap to avoid context overflow on small models
        revision_instructions=REVISION_INSTRUCTIONS_TEMPLATE,
    )

    critic_model   = cfg.get("critic", {}).get("model", "qwen2.5:1.5b")
    critic_temp    = cfg.get("critic", {}).get("temperature", 0.1)
    ollama_timeout = cfg.get("timeouts", {}).get("ollama_generate", 600)

    log.info("[CRITIC] %s — %s", clause_id, clause_name)
    verdict = run_reviewer_agent(cfg["llm"]["base_url"], critic_model, prompt, critic_temp, timeout=ollama_timeout)
    # Overwrite clause identity from known values rather than trusting the model's echo —
    # same anti-hallucination principle used elsewhere in this codebase.
    verdict = verdict.model_copy(update={"clause_id": clause_id, "clause_name": clause_name})
    assessment = verdict.overall_assessment
    result = verdict_to_markdown(verdict)
    log.info("[CRITIC RESULT] %s → %s", clause_id, assessment)

    critic_file.write_text(result, encoding="utf-8")
    critic_json_file.write_text(verdict.model_dump_json(indent=2), encoding="utf-8")
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
