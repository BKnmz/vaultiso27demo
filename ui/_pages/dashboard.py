"""Dashboard page — certification progress overview."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime

from core import (
    CLAUSE_NAMES, STATUS_KIND, REVIEW_RESULT, OUTPUTS_DIR,
    completion_stats, get_clause_status, get_review_assessment,
    load_org, export_all_to_excel, read_log_tail,
)
from components import page_head, pill, finding_html, meta_row_html, stepper_html
from icons import icon


def render() -> None:
    total, counts = completion_stats()
    pct = int(counts["APPROVED"] / total * 100) if total else 0
    approved  = counts["APPROVED"]
    needs_att = counts["DRAFT"] + counts["REVISION"]

    org = load_org()

    # ── Actions ──────────────────────────────────────────────────────────
    org_complete = bool(org.get("name"))
    docs_exist   = any((OUTPUTS_DIR / f"{cid}.md").exists() for cid in CLAUSE_NAMES)

    actions = (
        f'<a href="?page=generate" target="_self" class="btn primary">'
        f'{icon("play", 14)}Continue setup</a>'
    )
    page_head(
        "Certification progress",
        "Track your ISO 27001 documents, reviewer findings, and readiness for audit.",
        actions,
    )

    # ── Stepper ──────────────────────────────────────────────────────────
    step_data = [
        {"num": 1, "state": "done" if org_complete else "current",
         "name": "Organization", "desc": "Profile complete" if org_complete else "Set up profile"},
        {"num": 2, "state": "done" if docs_exist else ("current" if org_complete else "pending"),
         "name": "Generate",
         "desc": f"{approved} / {total} documents" if docs_exist else "Create documents"},
        {"num": 3, "state": "current" if (docs_exist and needs_att > 0) else ("done" if approved == total and docs_exist else "pending"),
         "name": "Review",
         "desc": f"{needs_att} awaiting review" if needs_att > 0 else "Approve documents"},
        {"num": 4, "state": "done" if (approved == total and total > 0) else "pending",
         "name": "Certify", "desc": "Submit to auditor"},
    ]
    st.markdown(
        '<div class="hint" style="margin-bottom:8px;font-size:12.5px;color:var(--ink-3)">'
        'How this works: <strong>1.</strong> Tell the AI about your company &nbsp;·&nbsp; '
        '<strong>2.</strong> AI writes 23 ISO 27001 documents &nbsp;·&nbsp; '
        '<strong>3.</strong> Read &amp; approve each one &nbsp;·&nbsp; '
        '<strong>4.</strong> Send the approved set to your auditor.'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(stepper_html(step_data), unsafe_allow_html=True)

    # ── Metrics row ───────────────────────────────────────────────────────
    # Annex A stats
    try:
        from core import load_annex_a, ANNEX_A_CONTROLS
        ev = load_annex_a()
        annex_impl = sum(
            1 for cid in ANNEX_A_CONTROLS
            if ev.get(cid, {}).get("applicable", True)
            and ev.get(cid, {}).get("status") == "Implemented"
        )
        annex_total = len(ANNEX_A_CONTROLS)
    except Exception:
        annex_impl, annex_total = 0, 93

    m1 = (
        f'<div class="metric">'
        f'<div class="metric-label">Readiness</div>'
        f'<div class="metric-value">{pct}<span class="unit">%</span></div>'
        f'<div class="progress accent" style="margin-top:10px"><div style="width:{pct}%"></div></div>'
        f'</div>'
    )
    m2 = (
        f'<div class="metric">'
        f'<div class="metric-label">Approved</div>'
        f'<div class="metric-value">{approved}<span class="unit">/ {total}</span></div>'
        f'<div class="metric-delta up">{icon("arrow", 12)}+{approved} this session</div>'
        f'</div>'
    )
    m3 = (
        f'<div class="metric">'
        f'<div class="metric-label">Needs attention</div>'
        f'<div class="metric-value">{needs_att}</div>'
        f'<div class="metric-delta">{counts["REVISION"]} flagged · {counts["DRAFT"]} in draft</div>'
        f'</div>'
    )
    m4 = (
        f'<div class="metric">'
        f'<div class="metric-label">Annex A implemented</div>'
        f'<div class="metric-value">{annex_impl}<span class="unit">/ {annex_total}</span></div>'
        f'<div class="metric-delta">{int(annex_impl/annex_total*100)}% of controls</div>'
        f'</div>'
    )
    st.markdown(
        f'<div class="metrics-row">{m1}{m2}{m3}{m4}</div>',
        unsafe_allow_html=True,
    )

    # ── Empty state helper ────────────────────────────────────────────────
    if not docs_exist:
        st.markdown(
            f'<div class="card"><div class="card-body" style="text-align:center;padding:32px">'
            f'<div style="color:var(--ink-3);font-size:13.5px">'
            f'Start by uploading your company document — '
            f'<a href="?page=org" target="_self" style="color:var(--accent)">Organization</a>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
        return

    # ── Main two-column layout ────────────────────────────────────────────
    col_left, col_right = st.columns([2, 1])

    with col_left:
        # Document table
        rows_html = ""
        for cid, name in CLAUSE_NAMES.items():
            status  = get_clause_status(cid)
            review  = get_review_assessment(cid)
            rlabel  = REVIEW_RESULT.get(review, ("—",))[0] if review else "—"
            rkind   = REVIEW_RESULT.get(review, ("—","info","neutral"))[2] if review else "neutral"
            f       = OUTPUTS_DIR / f"{cid}.md"
            words   = len(f.read_text(encoding="utf-8", errors="replace").split()) if f.exists() else 0
            w_str   = f'<span class="mono" style="float:right">{words}</span>' if words else '<span style="color:var(--ink-4)">—</span>'
            rev_pill = pill(rkind, rlabel, dot=False) if review else '<span class="muted">—</span>'
            rows_html += (
                f'<tr>'
                f'<td class="sec">{cid}</td>'
                f'<td class="name">{name}</td>'
                f'<td>{pill(STATUS_KIND.get(status,"neutral"), status.title())}</td>'
                f'<td>{rev_pill}</td>'
                f'<td style="text-align:right">{w_str}</td>'
                f'</tr>'
            )

        filter_btn = (
            f'<div class="row" style="gap:8px">'
            f'<button class="btn sm ghost">{icon("filter",12)} Filter</button>'
            f'</div>'
        )
        table_html = (
            f'<div class="card">'
            f'<div class="card-head"><h3 class="card-title">Documents</h3>{filter_btn}</div>'
            f'<div class="card-body flush">'
            f'<table class="tbl"><thead><tr>'
            f'<th style="width:64px">§</th>'
            f'<th>Document</th>'
            f'<th style="width:140px">Status</th>'
            f'<th style="width:160px">AI review</th>'
            f'<th style="width:70px;text-align:right">Words</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table>'
            f'</div></div>'
        )
        st.markdown(table_html, unsafe_allow_html=True)

        # Excel download (keep functional)
        _org_bulk = load_org()
        xlsx = export_all_to_excel(org_name=_org_bulk.get("name", ""))
        st.download_button(
            "Download tracker (.xlsx)",
            data=xlsx,
            file_name=f"VaultISO27_ISMS_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="One spreadsheet listing every ISO 27001 document and its current status.",
        )

    with col_right:
        # Reviewer activity
        _build_reviewer_activity()
        # Engine status
        _build_engine_status()


def _build_reviewer_activity() -> None:
    """Show last 3 reviewer findings as finding cards."""
    from core import CLAUSE_NAMES, get_review_assessment, get_review_text, REVIEW_RESULT

    findings_html = ""
    count = 0
    for cid in CLAUSE_NAMES:
        if count >= 3:
            break
        rev_code = get_review_assessment(cid)
        if not rev_code or rev_code == "PASS":
            continue
        rev_text = get_review_text(cid)
        label, _, kind = REVIEW_RESULT.get(rev_code, ("Not Reviewed", "info", "neutral"))
        snippet = ""
        if rev_text:
            for ln in rev_text.splitlines():
                stripped = ln.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("**"):
                    snippet = stripped[:120] + ("…" if len(stripped) > 120 else "")
                    break
        findings_html += finding_html(
            kind,
            f"{cid} · {CLAUSE_NAMES[cid]}",
            snippet or label,
            badge=label,
        )
        count += 1

    if not findings_html:
        findings_html = '<div style="color:var(--ink-3);font-size:13px">No reviewer findings yet.</div>'

    st.markdown(
        f'<div class="card" style="margin-bottom:16px">'
        f'<div class="card-head"><h3 class="card-title">Reviewer activity</h3></div>'
        f'<div class="card-body">{findings_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _build_engine_status() -> None:
    from core import load_config, get_ollama_models
    try:
        cfg = load_config()
    except Exception:
        return

    gen_model  = cfg.get("llm", {}).get("model", "—")
    rev_model  = cfg.get("critic", {}).get("model", "—")
    base_url   = cfg.get("llm", {}).get("base_url", "localhost:11434")
    models     = get_ollama_models(base_url)
    status_str = f"{len(models)} models" if models else "Offline"

    rows = (
        meta_row_html("Generator", gen_model) +
        meta_row_html("Reviewer",  rev_model) +
        meta_row_html("Mode",      "On-premises") +
        meta_row_html("Engine",    status_str) +
        meta_row_html("Base URL",  base_url)
    )
    st.markdown(
        f'<div class="card">'
        f'<div class="card-head"><h3 class="card-title">Engine status</h3></div>'
        f'<div class="card-body tight">{rows}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
