"""Documents page — export hub."""
from __future__ import annotations
import sys
import io
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import streamlit as st
from datetime import datetime

from core import (
    CLAUSE_NAMES, STATUS_KIND, REVIEW_RESULT, OUTPUTS_DIR,
    get_clause_status, get_review_assessment, read_output,
    load_org, load_config, export_clause_to_word, export_all_to_excel,
    export_soa_to_excel, upload_clause_to_github, _get_personnel_for_doc,
    load_annex_a,
)
from components import page_head, pill
from icons import icon


def _build_zip_of_all_docx(generated: list[tuple[str, str]], org: dict) -> bytes:
    """Bundle every generated clause as .docx into a single zip in memory."""
    pb, rvb, apb = _get_personnel_for_doc(org)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for cid, name in generated:
            content = read_output(cid)
            if not content:
                continue
            docx_bytes = export_clause_to_word(
                cid, content, org_name=org.get("name", ""),
                prepared_by=pb, reviewed_by=rvb, approved_by=apb,
            )
            safe_name = name.replace(" ", "_").replace("/", "_")
            zf.writestr(f"{cid}_{safe_name}.docx", docx_bytes)
    return buf.getvalue()


def render() -> None:
    generated = [
        (cid, name) for cid, name in CLAUSE_NAMES.items()
        if (OUTPUTS_DIR / f"{cid}.md").exists()
    ]

    org = load_org()
    cfg = load_config()
    gh_cfg = cfg.get("github", {})
    has_github = bool(gh_cfg.get("token") and gh_cfg.get("repo"))

    gh_action = f'<a href="?page=org" target="_self" class="btn">{icon("git",14)} Upload to GitHub</a>' if has_github else ""
    page_head(
        "Documents",
        "Download your completed ISMS documents as Word files, or a full Excel tracker for your auditor.",
        gh_action,
    )

    if not generated:
        st.info("No documents yet. Go to Generate first.")
        return

    # ── Export cards (3 across top) ───────────────────────────────────────
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            f'<div class="card"><div class="card-body">'
            f'<div style="display:flex;align-items:center;gap:14px">'
            f'<div style="width:48px;height:48px;border-radius:10px;background:var(--accent-soft);'
            f'color:var(--accent-ink);display:grid;place-items:center;flex:none">'
            f'{icon("doc", 22)}</div>'
            f'<div style="flex:1"><div style="font-size:14px;font-weight:600">Word documents</div>'
            f'<div class="hint">All generated clauses as a single .zip of .docx files</div></div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
        zip_bytes = _build_zip_of_all_docx(generated, org)
        st.download_button(
            "⬇ Download all (.zip)",
            data=zip_bytes,
            file_name=f"VaultISO27_Word_{datetime.now().strftime('%Y%m%d')}.zip",
            mime="application/zip",
            key="dl_word_zip",
            help="Download every ISO 27001 document as Word files in one zip archive.",
        )

    with c2:
        xlsx = export_all_to_excel(org_name=org.get("name", ""))
        st.markdown(
            f'<div class="card"><div class="card-body">'
            f'<div style="display:flex;align-items:center;gap:14px">'
            f'<div style="width:48px;height:48px;border-radius:10px;background:var(--ok-soft);'
            f'color:oklch(0.38 0.10 155);display:grid;place-items:center;flex:none">'
            f'{icon("grid", 22)}</div>'
            f'<div style="flex:1"><div style="font-size:14px;font-weight:600">Excel ISMS tracker</div>'
            f'<div class="hint">Single file, one sheet per clause, status tracking</div></div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
        st.download_button(
            "⬇ Download",
            data=xlsx,
            file_name=f"VaultISO27_ISMS_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_excel_top",
            help="Single Excel file with one sheet per ISO 27001 document. Useful for auditors.",
        )

    with c3:
        ev = load_annex_a()
        soa = export_soa_to_excel(
            json.dumps(ev, sort_keys=True),
            org_name=org.get("name", ""),
        )
        st.markdown(
            f'<div class="card"><div class="card-body">'
            f'<div style="display:flex;align-items:center;gap:14px">'
            f'<div style="width:48px;height:48px;border-radius:10px;background:var(--warn-soft);'
            f'color:oklch(0.42 0.12 75);display:grid;place-items:center;flex:none">'
            f'{icon("shield", 22)}</div>'
            f'<div style="flex:1"><div style="font-size:14px;font-weight:600">Statement of Applicability</div>'
            f'<div class="hint">93 Annex A controls with evidence references</div></div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
        st.download_button(
            "⬇ Export",
            data=soa,
            file_name=f"VaultISO27_SoA_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_soa_top",
            help="Statement of Applicability — lists all 93 Annex A controls and their evidence. A key audit document.",
        )

    # ── All documents table ───────────────────────────────────────────────
    search = st.text_input(
        "Search clause or title", placeholder="e.g. 5.2 or Policy",
        label_visibility="collapsed",
        help="Type a clause number (5.2) or part of a document title to filter the list.",
    )

    st.markdown(
        '<div class="card"><div class="card-head">'
        '<h3 class="card-title">All documents</h3></div>'
        '<div class="card-body">',
        unsafe_allow_html=True,
    )

    # Header row — column ratios match per-row buttons below for alignment
    col_widths = [1, 5, 2, 2, 2]
    h = st.columns(col_widths)
    h[0].markdown('<div class="muted mono" style="font-size:11px">§</div>', unsafe_allow_html=True)
    h[1].markdown('<div class="muted" style="font-size:11px;font-weight:600">DOCUMENT</div>', unsafe_allow_html=True)
    h[2].markdown('<div class="muted" style="font-size:11px;font-weight:600">STATUS</div>', unsafe_allow_html=True)
    h[3].markdown('<div class="muted" style="font-size:11px;font-weight:600">MODIFIED</div>', unsafe_allow_html=True)
    h[4].markdown('<div class="muted" style="font-size:11px;font-weight:600;text-align:right">EXPORT</div>', unsafe_allow_html=True)

    pb, rvb, apb = _get_personnel_for_doc(org)
    for cid, name in generated:
        if search and search.lower() not in cid.lower() and search.lower() not in name.lower():
            continue
        status  = get_clause_status(cid)
        content = read_output(cid)
        f       = OUTPUTS_DIR / f"{cid}.md"
        mod_str = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d %b, %H:%M") if f.exists() else "—"

        r = st.columns(col_widths)
        r[0].markdown(f'<div class="mono" style="font-size:12.5px;color:var(--ink-2)">{cid}</div>',
                      unsafe_allow_html=True)
        r[1].markdown(f'<div style="font-size:13px">{name}</div>', unsafe_allow_html=True)
        r[2].markdown(pill(STATUS_KIND.get(status, "neutral"), status.title()),
                      unsafe_allow_html=True)
        r[3].markdown(f'<div class="muted mono" style="font-size:12px">{mod_str}</div>',
                      unsafe_allow_html=True)
        with r[4]:
            if content:
                st.download_button(
                    "⬇ .docx",
                    data=export_clause_to_word(
                        cid, content, org_name=org.get("name", ""),
                        prepared_by=pb, reviewed_by=rvb, approved_by=apb,
                    ),
                    file_name=f"{cid}_{name.replace(' ', '_')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"dl_{cid}",
                    use_container_width=True,
                    help=f"Download {cid} as a Word document.",
                )

    st.markdown('</div></div>', unsafe_allow_html=True)

    # ── Bulk GitHub upload ────────────────────────────────────────────────
    if has_github:
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        if st.button(
            "⬆ Upload all to GitHub", key="gh_bulk",
            help="Save every generated document to your configured GitHub repository.",
        ):
            _bulk_cfg = load_config()
            results = []
            with st.spinner("Uploading to GitHub…"):
                for cid, _ in generated:
                    c = read_output(cid)
                    if c:
                        ok, msg = upload_clause_to_github(cid, c, _bulk_cfg)
                        results.append((cid, ok, msg))
            passed = sum(1 for _, ok, _ in results if ok)
            st.success(f"Uploaded {passed}/{len(results)} files to GitHub.")
