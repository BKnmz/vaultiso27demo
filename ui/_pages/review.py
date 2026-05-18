"""Review page — approve or flag documents."""
from __future__ import annotations
import sys
import json
import html as _html
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime

from core import (
    CLAUSE_NAMES, STATUS_KIND, REVIEW_RESULT, OUTPUTS_DIR,
    get_clause_status, save_status, get_review_assessment, get_review_text,
    read_output, load_org, load_config, run_reviewer_subprocess,
    export_clause_to_word, _get_personnel_for_doc,
)
import pipeline as _pipeline
from components import page_head, pill
from icons import icon


_STATUS_PILL_KIND = {
    "PASS": "ok",
    "FAIL": "err",
    "CONDITIONAL": "warn",
    "CONDITIONAL PASS": "warn",
}


def _parse_findings_table(rev_text: str) -> list[dict]:
    """Parse the ### Findings Table block into [{dim, status, finding}, ...]."""
    rows: list[dict] = []
    in_table = False
    for ln in rev_text.splitlines():
        if "### Findings Table" in ln:
            in_table = True
            continue
        if in_table and ln.strip().startswith("###"):
            break
        if not in_table:
            continue
        s = ln.strip()
        if not s.startswith("|"):
            continue
        # Skip header & separator rows
        if re.match(r"^\|\s*[-:|\s]+\|", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        dim, status, finding = cells[0], cells[1], " | ".join(cells[2:])
        if dim.lower() in ("dimension", ""):
            continue
        rows.append({"dimension": dim, "status": status, "finding": finding})
    return rows


def _parse_required_revisions(rev_text: str) -> list[str]:
    """Parse the ### Required Revisions block into ordered action items."""
    items: list[str] = []
    in_block = False
    for ln in rev_text.splitlines():
        if "### Required Revisions" in ln:
            in_block = True
            continue
        if in_block and ln.strip().startswith("###"):
            break
        if not in_block:
            continue
        s = ln.strip()
        if not s:
            continue
        # Strip leading list markers (1. / 2) / - / *)
        s = re.sub(r"^(\d+[\.\)]|\-|\*)\s*", "", s)
        if s:
            items.append(s)
    return items


def _render_reviewer_findings(rev_text: str) -> str:
    """Convert reviewer markdown into a styled task list with PASS/FAIL pills."""
    findings = _parse_findings_table(rev_text)
    revisions = _parse_required_revisions(rev_text)

    # Detect verdict to decide whether to surface revisions callout
    verdict = ""
    for ln in rev_text.splitlines():
        if "**Overall Assessment:**" in ln:
            up = ln.upper()
            if "FAIL" in up:
                verdict = "FAIL"
            elif "CONDITIONAL" in up:
                verdict = "CONDITIONAL"
            elif "PASS" in up:
                verdict = "PASS"
            break

    out: list[str] = []

    # "What needs fixing" callout for non-PASS verdicts
    if verdict in ("FAIL", "CONDITIONAL") and revisions:
        items_html = "".join(
            f'<li style="margin-bottom:6px">{_html.escape(r)}</li>'
            for r in revisions[:3]
        )
        kind = _STATUS_PILL_KIND.get(verdict, "warn")
        out.append(
            f'<div class="finding {kind}" style="margin-bottom:12px">'
            f'<div class="f-head" style="margin-bottom:6px">'
            f'<span class="f-title">What needs fixing</span>'
            f'<span class="pill {kind}" style="font-size:11px;padding:1px 6px">'
            f'{verdict.title()}</span></div>'
            f'<ol style="margin:0;padding-left:18px;font-size:12.5px;line-height:1.5;color:var(--ink-2)">'
            f'{items_html}</ol></div>'
        )

    # Findings table → bullet/task list
    if findings:
        rows_html = ""
        for f in findings[:20]:
            up = f["status"].upper()
            if "FAIL" in up:
                kind = "err"
            elif "CONDITIONAL" in up:
                kind = "warn"
            elif "PASS" in up:
                kind = "ok"
            else:
                kind = "neutral"
            badge = pill(kind, _html.escape(f["status"]), dot=False)
            rows_html += (
                f'<li style="display:flex;gap:8px;align-items:flex-start;'
                f'padding:6px 0;border-bottom:1px solid var(--border)">'
                f'<div style="flex:1">'
                f'<div style="font-size:12px;font-weight:600;color:var(--ink-2);'
                f'margin-bottom:2px">{_html.escape(f["dimension"])}</div>'
                f'<div style="font-size:12px;color:var(--ink-2);line-height:1.4">'
                f'{_html.escape(f["finding"])}</div></div>'
                f'<div style="flex:none">{badge}</div>'
                f'</li>'
            )
        out.append(
            f'<ul style="list-style:none;margin:0;padding:0">{rows_html}</ul>'
        )
    elif not out:
        # No structured findings parsed — show plain text fallback
        snippet = _html.escape(rev_text[:600])
        out.append(
            f'<div style="font-size:12px;color:var(--ink-3);white-space:pre-wrap">'
            f'{snippet}</div>'
        )

    return "".join(out)


def render() -> None:
    cfg = load_config()
    reviewer_enabled = cfg.get("critic", {}).get("enabled", False)

    pending = [
        cid for cid in CLAUSE_NAMES
        if get_clause_status(cid) in ("DRAFT", "REVISION")
        and (OUTPUTS_DIR / f"{cid}.md").exists()
    ]

    if not pending:
        page_head("Review & approve", "Step 3 — All documents have been approved.")
        st.success("All generated documents have been reviewed and approved. Download them in Documents.")
        return

    pending_pill = pill("err", str(len(pending)), dot=False)
    page_head(
        "Review & approve",
        "Step 3 — Read each document, check the AI reviewer's findings, then approve or flag.",
    )

    col_queue, col_viewer = st.columns([1, 3])

    # ── Pending queue (left) ──────────────────────────────────────────────
    with col_queue:
        selected = st.session_state.get("review_selected", pending[0])
        if selected not in pending:
            selected = pending[0]

        queue_html = ""
        for cid in pending:
            status  = get_clause_status(cid)
            review  = get_review_assessment(cid)
            kind    = REVIEW_RESULT.get(review, ("—","info","neutral"))[2] if review else "neutral"
            rlabel  = REVIEW_RESULT.get(review, ("—",))[0] if review else "Not reviewed"
            is_sel  = cid == selected
            bg      = "background:var(--surface-2);border:1px solid var(--border-2);" if is_sel else "border:1px solid transparent;"
            mod_time = ""
            f = OUTPUTS_DIR / f"{cid}.md"
            if f.exists():
                try:
                    ts = datetime.fromtimestamp(f.stat().st_mtime)
                    mod_time = ts.strftime("%H:%M")
                except Exception:
                    pass
            queue_html += (
                f'<a href="?page=review&sel={cid}" target="_self" style="text-decoration:none">'
                f'<div style="padding:10px 12px;border-radius:6px;cursor:pointer;{bg};margin-bottom:4px">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px">'
                f'<span class="mono" style="font-size:11px;color:var(--ink-3)">{cid}</span>'
                f'{pill(kind, rlabel, dot=False)}'
                f'</div>'
                f'<div style="font-size:13px;color:var(--ink);font-weight:500;line-height:1.3">'
                f'{CLAUSE_NAMES[cid]}</div>'
                f'<div style="font-size:11px;color:var(--ink-4);margin-top:2px">{mod_time}</div>'
                f'</div></a>'
            )

        st.markdown(
            f'<div class="card">'
            f'<div class="card-head"><h3 class="card-title">Pending</h3>{pending_pill}</div>'
            f'<div class="card-body flush" style="padding:6px">{queue_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Handle selection from URL param ──────────────────────────────────
    url_sel = st.query_params.get("sel", "")
    if url_sel and url_sel in pending:
        selected = url_sel
        st.session_state["review_selected"] = selected

    # ── Document viewer (right) ───────────────────────────────────────────
    with col_viewer:
        content  = read_output(selected)
        status   = get_clause_status(selected)
        rev_text = get_review_text(selected)
        rev_code = get_review_assessment(selected)
        rlabel, rtype, rkind = REVIEW_RESULT.get(rev_code, ("Not Reviewed","info","neutral")) if rev_code else ("Not Reviewed","info","neutral")

        # Card header
        f = OUTPUTS_DIR / f"{selected}.md"
        mod_str = ""
        if f.exists():
            try:
                mod_str = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d %b, %H:%M")
            except Exception:
                pass

        # Card header
        st.markdown(
            f'<div class="card" style="overflow:hidden;margin-bottom:8px">'
            f'<div style="padding:14px 20px;display:flex;align-items:center;gap:12px">'
            f'<span class="mono muted" style="font-size:12px">Clause {selected}</span>'
            f'<h3 class="card-title" style="flex:1">{CLAUSE_NAMES.get(selected,"")}</h3>'
            f'{pill(STATUS_KIND.get(status,"neutral"), status.title())}'
            f'<span class="spacer"></span>'
            f'<span class="muted" style="font-size:12px">{mod_str}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # AI Reviewer findings (full-width card)
        findings_html = _render_reviewer_findings(rev_text) if rev_text else ""
        st.markdown(
            f'<div class="card" style="margin-bottom:8px">'
            f'<div class="card-head">'
            f'<h3 class="card-title">AI Reviewer</h3>'
            f'{pill(rkind, rlabel, dot=False)}'
            f'</div>'
            f'<div class="card-body" style="padding:14px">'
            f'{findings_html if findings_html else "<p style=\'color:var(--ink-3);font-size:12px\'>No AI review available. Run the AI Reviewer to see findings.</p>"}'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        notes_key = f"notes_{selected}"
        notes = st.text_area(
            "Decision notes (optional)",
            key=notes_key,
            placeholder="e.g. Routing back to CISO for NIS2 paragraph…",
            label_visibility="collapsed",
            help="Add notes before approving or flagging. Notes are stored and shown in Version History.",
        )

        ca, cb, cc = st.columns(3)
        with ca:
            if st.button(
                "Approve", key=f"approve_{selected}", type="primary",
                use_container_width=True,
                help="Mark this document as final. It will appear with green status on the Dashboard.",
            ):
                save_status(selected, "APPROVED", notes)
                st.success(f"Document {selected} approved.")
                st.rerun()
        with cb:
            if st.button(
                "Flag for revision", key=f"flag_{selected}", use_container_width=True,
                help="Send this document back. Add notes explaining what needs to change.",
            ):
                save_status(selected, "REVISION", notes)
                if notes.strip():
                    cfg_for_note = load_config()
                    _pipeline.write_review_note_event(selected, notes, cfg_for_note)
                st.warning(f"Document {selected} flagged for revision.")
                st.rerun()

        _sf = OUTPUTS_DIR / f"{selected}.status.json"
        _status_data = {}
        if _sf.exists():
            try:
                _status_data = json.loads(_sf.read_text(encoding="utf-8"))
            except Exception:
                pass
        if (
            _status_data.get("status") == "REVISION"
            and _status_data.get("notes", "").strip()
        ):
            if st.button(
                "🔁 Re-generate using my notes", key=f"regen_{selected}",
                use_container_width=True,
                help="AI rewrites this document using the notes above as direct instructions, then re-runs the AI Reviewer.",
            ):
                cfg = load_config()
                org = load_org()
                with st.spinner("Re-generating with your reviewer notes… this may take a few minutes."):
                    ok, msg = _pipeline.regenerate_with_user_notes(selected, cfg, org)
                st.cache_data.clear()
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

        with cc:
            if content:
                org = load_org()
                pb, rvb, apb = _get_personnel_for_doc(org)
                docx_bytes = export_clause_to_word(
                    selected, content, org_name=org.get("name", ""),
                    prepared_by=pb, reviewed_by=rvb, approved_by=apb,
                )
                st.download_button(
                    "⬇ Word",
                    data=docx_bytes,
                    file_name=f"{selected}_{CLAUSE_NAMES.get(selected,'').replace(' ','_')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"dl_rev_{selected}",
                    use_container_width=True,
                    help="Download this document as a Word file with your company header and approval block.",
                )

        if reviewer_enabled:
            if st.button(
                "Re-run AI review", key=f"rerun_{selected}",
                help="Ask the AI Reviewer to check this document again. Useful after editing the company profile.",
            ):
                with st.spinner("Running AI review…"):
                    ok, log = run_reviewer_subprocess(selected)
                (st.success if ok else st.error)("Review updated." if ok else log[:400])
                if ok:
                    st.rerun()
        elif not rev_text:
            st.caption("Enable the AI Reviewer in Organization > AI Engine to use this feature.")

        # Generated document (collapsible — keeps actions visible without scrolling)
        doc_body_html = ""
        if content:
            paras = []
            for line in content.splitlines():
                s = line.strip()
                if s.startswith("# "):
                    paras.append(f'<h1>{_html.escape(s[2:])}</h1>')
                elif s.startswith("## "):
                    paras.append(f'<h2>{_html.escape(s[3:])}</h2>')
                elif s.startswith("### "):
                    paras.append(f'<h2 style="font-size:14px">{_html.escape(s[4:])}</h2>')
                elif s.startswith("- ") or s.startswith("* "):
                    paras.append(f'<li>{_html.escape(s[2:])}</li>')
                elif s == "---" or s == "":
                    paras.append("<br>")
                elif s:
                    paras.append(f'<p>{_html.escape(s)}</p>')
            doc_body_html = "\n".join(paras)
        else:
            doc_body_html = '<p style="color:var(--ink-3)">Document content not found.</p>'

        with st.expander("📄 Generated document", expanded=False):
            st.markdown(doc_body_html, unsafe_allow_html=True)

        # Version history
        vers_file = OUTPUTS_DIR / f"{selected}.versions.json"
        if vers_file.exists():
            try:
                versions = json.loads(vers_file.read_text(encoding="utf-8"))
            except Exception:
                versions = []
            if versions:
                with st.expander("Version History"):
                    for v in reversed(versions):
                        vc1, vc2 = st.columns([5, 1])
                        with vc1:
                            ts = v.get("timestamp", "")[:16].replace("T", " ")
                            ev = v.get("event", "generation")
                            if ev == "review_note":
                                note_preview = v.get("note", "")[:60]
                                ellipsis = "..." if len(v.get("note", "")) > 60 else ""
                                event_tag = f' · 📝 "{note_preview}{ellipsis}"'
                            elif ev == "user_regen":
                                event_tag = " · 🔁 Regenerated"
                            else:
                                event_tag = ""
                            st.caption(f"v{v['version']}  ·  {ts}{event_tag}")
                        with vc2:
                            if st.button("Restore", key=f"restore_{selected}_v{v['version']}",
                                         use_container_width=True):
                                (OUTPUTS_DIR / f"{selected}.md").write_text(
                                    v["content"], encoding="utf-8"
                                )
                                hf = OUTPUTS_DIR / f"{selected}.hash"
                                if hf.exists():
                                    hf.unlink()
                                st.success(f"Restored to v{v['version']}.")
                                st.rerun()
