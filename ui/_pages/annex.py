"""Annex A controls page — evidence tracker and SoA export."""
from __future__ import annotations
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime

from core import (
    ANNEX_A_CONTROLS, ANNEX_A_THEMES, ANNEX_A_STATUSES,
    load_annex_a, save_annex_a, export_soa_to_excel,
    _annex_collect_from_state, load_org,
)
from components import page_head, pill
from icons import icon


_STATUS_CHIP = {
    "Implemented":  "impl",
    "Partial":      "part",
    "Planned":      "plan",
    "Not Assessed": "",
}
_STATUS_PILL = {
    "Implemented": "ok",
    "Partial":     "warn",
    "Planned":     "info",
    "Not Assessed": "neutral",
}


def render() -> None:
    evidence = load_annex_a()
    org = load_org()

    # ── Metrics ───────────────────────────────────────────────────────────
    total     = len(ANNEX_A_CONTROLS)
    app_count = sum(1 for cid in ANNEX_A_CONTROLS if evidence.get(cid, {}).get("applicable", True))
    excl      = total - app_count
    impl      = sum(1 for cid in ANNEX_A_CONTROLS
                    if evidence.get(cid, {}).get("applicable", True)
                    and evidence.get(cid, {}).get("status") == "Implemented")
    partial   = sum(1 for cid in ANNEX_A_CONTROLS
                    if evidence.get(cid, {}).get("applicable", True)
                    and evidence.get(cid, {}).get("status") == "Partial")
    planned   = sum(1 for cid in ANNEX_A_CONTROLS
                    if evidence.get(cid, {}).get("applicable", True)
                    and evidence.get(cid, {}).get("status") == "Planned")

    # ── Page actions ──────────────────────────────────────────────────────
    soa_bytes = export_soa_to_excel(
        json.dumps(evidence, sort_keys=True),
        org_name=org.get("name", ""),
    )

    page_head(
        "Annex A controls",
        "Track evidence and applicability for all 93 ISO 27001:2022 Annex A controls. "
        "Export as a Statement of Applicability for your auditor.",
    )

    # ── SoA download (Streamlit widget, above HTML) ───────────────────────
    col_dl, col_save, _ = st.columns([2, 2, 6])
    with col_dl:
        st.download_button(
            "⬇ Export SoA (.xlsx)",
            data=soa_bytes,
            file_name=f"VaultISO27_SoA_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Download the Statement of Applicability — a key audit document listing every Annex A control and your evidence.",
        )
    with col_save:
        if st.button(
            "Save changes", type="primary", key="save_annex_top",
            help="Save your applicability and status decisions for all 93 controls.",
        ):
            save_annex_a(_annex_collect_from_state())
            export_soa_to_excel.clear()
            st.success("Annex A evidence saved.")
            st.rerun()

    # ── 6-column metrics ──────────────────────────────────────────────────
    metrics = [
        ("Total",        total,    "",    ""),
        ("Applicable",   app_count,"",    "ok"),
        ("Implemented",  impl,     f"{int(impl/app_count*100)}%" if app_count else "0%", "ok"),
        ("Partial",      partial,  "",    "warn"),
        ("Planned",      planned,  "",    "info"),
        ("Excluded",     excl,     "",    "neutral"),
    ]
    m_html = ""
    for label, val, sub, kind in metrics:
        unit = f'<span class="unit">{sub}</span>' if sub else ""
        m_html += (
            f'<div class="metric">'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-value">{val}{unit}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="metrics-row" style="grid-template-columns:repeat(6,1fr)">{m_html}</div>',
        unsafe_allow_html=True,
    )

    # ── Two-column layout ─────────────────────────────────────────────────
    col_map, col_detail = st.columns([1.4, 1])

    # ── Control map (left) ────────────────────────────────────────────────
    with col_map:
        legend = (
            f'{pill("ok","Implemented")} {pill("warn","Partial")} '
            f'{pill("info","Planned")} {pill("neutral","N/A",dot=False)}'
        )
        chips_html = ""
        for theme_id, theme_name in ANNEX_A_THEMES.items():
            controls = [(cid, ctrl) for cid, ctrl in ANNEX_A_CONTROLS.items()
                        if ctrl["theme"] == theme_id]
            grid_items = ""
            for cid, ctrl in controls:
                e = evidence.get(cid, {})
                applicable = e.get("applicable", True)
                if not applicable:
                    chip_cls = "na"
                else:
                    chip_cls = _STATUS_CHIP.get(e.get("status", ""), "")
                sel_cls = " selected" if st.session_state.get("annex_sel") == cid else ""
                ctrl_name = ctrl["name"]
                grid_items += (
                    f'<a href="?page=annex&ctrl={cid}" target="_self" style="text-decoration:none">'
                    f'<div class="annex-chip {chip_cls}{sel_cls}" title="{cid} — {ctrl_name}">'
                    f'{cid}</div></a>'
                )
            chips_html += (
                f'<div style="margin-bottom:20px">'
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
                f'<div class="mono" style="font-size:12px;color:var(--ink-3)">Theme {theme_id}</div>'
                f'<div style="font-size:13px;font-weight:600">{theme_name}</div>'
                f'<div class="muted" style="font-size:12px">· {len(controls)} controls</div>'
                f'</div>'
                f'<div class="annex-grid">{grid_items}</div>'
                f'</div>'
            )

        st.markdown(
            f'<div class="card">'
            f'<div class="card-head"><h3 class="card-title">Control map</h3>'
            f'<div class="row" style="gap:8px;font-size:12px">{legend}</div></div>'
            f'<div class="card-body">{chips_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Detail panel (right) ──────────────────────────────────────────────
    with col_detail:
        # Selected control from URL
        url_ctrl = st.query_params.get("ctrl", "")
        if url_ctrl and url_ctrl in ANNEX_A_CONTROLS:
            st.session_state["annex_sel"] = url_ctrl

        sel_cid = st.session_state.get("annex_sel", list(ANNEX_A_CONTROLS.keys())[0])
        if sel_cid not in ANNEX_A_CONTROLS:
            sel_cid = list(ANNEX_A_CONTROLS.keys())[0]

        ctrl = ANNEX_A_CONTROLS[sel_cid]
        e    = evidence.get(sel_cid, {})
        applicable = e.get("applicable", True)
        status     = e.get("status", "Not Assessed")
        justif     = e.get("justification", "")
        evid_refs  = "\n".join(e.get("evidence_refs", []))

        status_pill = pill(_STATUS_PILL.get(status, "neutral"), status)
        st.markdown(
            f'<div class="card" style="margin-bottom:16px">'
            f'<div class="card-head">'
            f'<h3 class="card-title">{sel_cid} · {ctrl["name"]}</h3>'
            f'{status_pill}</div>'
            f'<div class="card-body">',
            unsafe_allow_html=True,
        )
        st.write(f'*{ctrl["name"]}* — Theme {ctrl["theme"]}: {ANNEX_A_THEMES.get(ctrl["theme"], "")}')

        new_applicable = st.toggle(
            "Applicable", value=applicable, key=f"annex_{sel_cid}_applicable",
            help="Turn off if this control does not apply to your organization. You will need to give a reason for exclusion in the SoA.",
        )

        if new_applicable:
            st.selectbox(
                "Status",
                ANNEX_A_STATUSES,
                index=ANNEX_A_STATUSES.index(status) if status in ANNEX_A_STATUSES else 0,
                key=f"annex_{sel_cid}_status",
                help="How far you've got with implementing this control.",
            )

        lbl = "Justification" if new_applicable else "Reason for exclusion"
        st.text_input(
            lbl, value=justif, key=f"annex_{sel_cid}_justification",
            placeholder="e.g. Covered by IT Security Policy v2.1",
            help="One short sentence the auditor will read. If applicable, point to the policy/document that implements this control.",
        )

        if new_applicable:
            st.text_area(
                "Evidence references", value=evid_refs,
                key=f"annex_{sel_cid}_evidence",
                placeholder="One file path or URL per line", height=80,
                help="List the documents, screenshots or system records that prove this control is in place.",
            )

        if st.button(
            "Save this control", key=f"save_ctrl_{sel_cid}", type="primary",
            help="Save your decisions for this single control.",
        ):
            save_annex_a(_annex_collect_from_state())
            export_soa_to_excel.clear()
            st.success(f"Saved {sel_cid}.")
            st.rerun()

        st.markdown('</div></div>', unsafe_allow_html=True)

        # Coverage by theme
        cov_html = ""
        for theme_id, theme_name in ANNEX_A_THEMES.items():
            theme_controls = [cid for cid, ctrl in ANNEX_A_CONTROLS.items() if ctrl["theme"] == theme_id]
            t_impl = sum(1 for cid in theme_controls
                         if evidence.get(cid, {}).get("applicable", True)
                         and evidence.get(cid, {}).get("status") == "Implemented")
            t_total = len(theme_controls)
            pct = int(t_impl / t_total * 100) if t_total else 0
            cov_html += (
                f'<div style="margin-bottom:12px">'
                f'<div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:4px">'
                f'<span><span class="mono muted">Theme {theme_id}</span> · {theme_name}</span>'
                f'<span class="mono">{t_impl}/{t_total}</span>'
                f'</div>'
                f'<div class="progress"><div style="width:{pct}%"></div></div>'
                f'</div>'
            )
        st.markdown(
            f'<div class="card">'
            f'<div class="card-head"><h3 class="card-title">Coverage by theme</h3></div>'
            f'<div class="card-body">{cov_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
