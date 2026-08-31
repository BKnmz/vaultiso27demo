"""Risk Register page — manual risk entry linked to Clause 6.1.2 / 6.1.3."""
from __future__ import annotations
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime

from core import (
    load_risk_register, save_risk_register, export_risk_register_to_excel,
)
from components import page_head, pill
from icons import icon

_TREATMENTS = ["Modify", "Retain", "Avoid", "Share"]
_STATUSES   = ["Open", "In Treatment", "Closed"]

_STATUS_PILL = {
    "Open":         "err",
    "In Treatment": "warn",
    "Closed":       "ok",
}


def _score_color(score: int) -> str:
    if score >= 15:
        return "var(--err)"
    if score >= 8:
        return "var(--warn)"
    return "var(--ok)"


def render() -> None:
    data = load_risk_register()

    # ── Page header ───────────────────────────────────────────────────────
    page_head(
        "Risk Register",
        "Record and track identified information security risks. "
        "Linked to Clause 6.1.2 (Risk Assessment) and 6.1.3 (Risk Treatment).",
    )

    st.info(
        "**How to use the Risk Register**\n\n"
        "Add each identified risk below. Likelihood and Impact are scored 1–5; the tool "
        "calculates the inherent risk score (Likelihood × Impact). Choose a treatment option "
        "(Modify / Retain / Avoid / Share) and map to Annex A controls. "
        "This register is the primary input for your ISO 27001 **Clause 6.1.2** and "
        "**Clause 6.1.3** documents — generate those clauses after populating risks here."
    )

    # ── Metrics ───────────────────────────────────────────────────────────
    total_risks  = len(data)
    open_count   = sum(1 for r in data if r.get("status", "Open") == "Open")
    treat_count  = sum(1 for r in data if r.get("status", "Open") == "In Treatment")
    closed_count = sum(1 for r in data if r.get("status", "Open") == "Closed")
    high_count   = sum(1 for r in data if r.get("inherent_score", 0) >= 15)

    m_html = ""
    for label, val in [
        ("Total risks", total_risks),
        ("Open", open_count),
        ("In Treatment", treat_count),
        ("Closed", closed_count),
        ("High risk (≥15)", high_count),
    ]:
        m_html += (
            f'<div class="metric">'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-value">{val}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="metrics-row" style="grid-template-columns:repeat(5,1fr)">{m_html}</div>',
        unsafe_allow_html=True,
    )

    # ── Add Risk form ─────────────────────────────────────────────────────
    with st.expander("Add new risk", expanded=(total_risks == 0)):
        with st.form("add_risk_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                asset_ref = st.text_input(
                    "Asset / System",
                    placeholder="e.g. CRM database, email server",
                    help="The information asset or system this risk relates to.",
                )
                threat = st.text_input(
                    "Threat",
                    placeholder="e.g. Ransomware attack",
                    help="What could go wrong — the threat scenario.",
                )
                vulnerability = st.text_input(
                    "Vulnerability",
                    placeholder="e.g. Unpatched OS, no backups",
                    help="The weakness that makes the threat possible.",
                )
                owner = st.text_input(
                    "Risk Owner",
                    placeholder="e.g. IT Manager",
                    help="The person accountable for managing this risk.",
                )
            with c2:
                likelihood = st.slider(
                    "Likelihood (1–5)", min_value=1, max_value=5, value=3,
                    help="1 = Very Unlikely, 5 = Very Likely.",
                )
                impact = st.slider(
                    "Impact (1–5)", min_value=1, max_value=5, value=3,
                    help="1 = Negligible, 5 = Catastrophic.",
                )
                treatment = st.selectbox(
                    "Treatment option",
                    _TREATMENTS,
                    help="Modify (reduce), Retain (accept), Avoid (stop activity), Share (insure/outsource).",
                )
                control_refs = st.text_input(
                    "Annex A control references",
                    placeholder="e.g. 8.7, 8.13, 5.23",
                    help="Comma-separated Annex A control IDs that address this risk.",
                )
            notes = st.text_area(
                "Notes",
                placeholder="Any additional context, decisions, or links to evidence.",
                height=70,
                help="Free-text field for audit trail notes.",
            )
            submitted = st.form_submit_button("Add risk", type="primary")
            if submitted:
                if not threat.strip():
                    st.error("Threat is required.")
                else:
                    score = likelihood * impact
                    refs = [r.strip() for r in control_refs.split(",") if r.strip()]
                    # Derive next ID from highest existing numeric suffix, not list length
                    max_id = 0
                    for risk in data:
                        try:
                            num = int(risk.get("id", "R000")[1:])  # Extract digits after 'R'
                            max_id = max(max_id, num)
                        except (ValueError, IndexError):
                            pass
                    new_risk = {
                        "id":             f"R{max_id + 1:03d}",
                        "asset_ref":      asset_ref.strip(),
                        "threat":         threat.strip(),
                        "vulnerability":  vulnerability.strip(),
                        "likelihood":     likelihood,
                        "impact":         impact,
                        "inherent_score": score,
                        "treatment":      treatment,
                        "control_refs":   refs,
                        "owner":          owner.strip(),
                        "residual_score": 0,
                        "status":         "Open",
                        "notes":          notes.strip(),
                        "created":        datetime.now().isoformat(),
                    }
                    data.append(new_risk)
                    save_risk_register(data)
                    st.success(f"Risk {new_risk['id']} added.")
                    st.rerun()

    # ── Export button ─────────────────────────────────────────────────────
    if data:
        col_dl, _ = st.columns([2, 8])
        with col_dl:
            st.download_button(
                "Export Register (.xlsx)",
                data=export_risk_register_to_excel(data),
                file_name=f"VaultISO27_RiskRegister_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Download the full risk register as a styled Excel workbook.",
            )

    # ── Risk table ────────────────────────────────────────────────────────
    if not data:
        st.markdown(
            '<div class="card"><div class="card-body" style="text-align:center;padding:32px;'
            'color:var(--ink-3);font-size:13.5px">No risks recorded yet. Use the form above to add your first risk.</div></div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        '<div style="font-size:12px;color:var(--ink-3);margin-bottom:8px;">'
        f'{total_risks} risk{"s" if total_risks != 1 else ""} recorded</div>',
        unsafe_allow_html=True,
    )

    # Header row
    hdr = st.columns([1, 3, 3, 2, 1, 1, 1, 1, 2])
    for col, label in zip(hdr, ["ID", "Threat", "Asset", "Treatment", "L", "I", "Score", "Status", "Actions"]):
        col.markdown(
            f'<div style="font-size:11.5px;font-weight:600;color:var(--ink-3);'
            f'text-transform:uppercase;letter-spacing:.05em;padding:6px 0;">{label}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:1px;background:var(--border);margin-bottom:4px;"></div>', unsafe_allow_html=True)

    for i, risk in enumerate(data):
        score   = risk.get("inherent_score", risk.get("likelihood", 1) * risk.get("impact", 1))
        status  = risk.get("status", "Open")
        spill   = _STATUS_PILL.get(status, "neutral")
        s_color = _score_color(score)

        cols = st.columns([1, 3, 3, 2, 1, 1, 1, 1, 2])
        cols[0].markdown(f'<span class="mono" style="font-size:12px">{risk.get("id","")}</span>', unsafe_allow_html=True)
        cols[1].markdown(f'<span style="font-size:13px;font-weight:500">{risk.get("threat","")}</span>', unsafe_allow_html=True)
        cols[2].markdown(f'<span style="font-size:12.5px;color:var(--ink-2)">{risk.get("asset_ref","") or "—"}</span>', unsafe_allow_html=True)
        cols[3].markdown(f'<span style="font-size:12.5px">{risk.get("treatment","")}</span>', unsafe_allow_html=True)
        cols[4].markdown(f'<span style="font-size:13px">{risk.get("likelihood",0)}</span>', unsafe_allow_html=True)
        cols[5].markdown(f'<span style="font-size:13px">{risk.get("impact",0)}</span>', unsafe_allow_html=True)
        cols[6].markdown(
            f'<span style="font-size:13px;font-weight:600;color:{s_color}">{score}</span>',
            unsafe_allow_html=True,
        )
        cols[7].markdown(pill(spill, status, dot=False), unsafe_allow_html=True)

        with cols[8]:
            action_cols = st.columns(2)
            with action_cols[0]:
                if st.button("Edit", key=f"edit_{i}_{risk.get('id','')}", help="Edit this risk"):
                    st.session_state[f"editing_risk_{i}"] = True
            with action_cols[1]:
                if st.button("Del", key=f"del_{i}_{risk.get('id','')}", help="Delete this risk"):
                    data.pop(i)
                    save_risk_register(data)
                    st.rerun()

        # Inline edit form
        if st.session_state.get(f"editing_risk_{i}"):
            with st.form(f"edit_form_{i}"):
                ec1, ec2 = st.columns(2)
                with ec1:
                    e_asset  = st.text_input("Asset / System", value=risk.get("asset_ref",""), key=f"e_asset_{i}")
                    e_threat = st.text_input("Threat", value=risk.get("threat",""), key=f"e_threat_{i}")
                    e_vuln   = st.text_input("Vulnerability", value=risk.get("vulnerability",""), key=f"e_vuln_{i}")
                    e_owner  = st.text_input("Risk Owner", value=risk.get("owner",""), key=f"e_owner_{i}")
                with ec2:
                    e_like   = st.slider("Likelihood", 1, 5, risk.get("likelihood",3), key=f"e_like_{i}")
                    e_impact = st.slider("Impact", 1, 5, risk.get("impact",3), key=f"e_impact_{i}")
                    e_treat  = st.selectbox("Treatment", _TREATMENTS,
                                            index=_TREATMENTS.index(risk.get("treatment","Modify")) if risk.get("treatment") in _TREATMENTS else 0,
                                            key=f"e_treat_{i}")
                    e_status = st.selectbox("Status", _STATUSES,
                                            index=_STATUSES.index(risk.get("status","Open")) if risk.get("status") in _STATUSES else 0,
                                            key=f"e_status_{i}")
                    e_ctrl   = st.text_input("Control refs", value=", ".join(risk.get("control_refs",[])), key=f"e_ctrl_{i}")
                    e_resid  = st.slider("Residual score", 0, 25, risk.get("residual_score",0), key=f"e_resid_{i}")
                e_notes  = st.text_area("Notes", value=risk.get("notes",""), height=60, key=f"e_notes_{i}")
                save_edit, cancel_edit = st.columns(2)
                with save_edit:
                    if st.form_submit_button("Save changes", type="primary"):
                        data[i] = {
                            **risk,
                            "asset_ref":      e_asset.strip(),
                            "threat":         e_threat.strip(),
                            "vulnerability":  e_vuln.strip(),
                            "owner":          e_owner.strip(),
                            "likelihood":     e_like,
                            "impact":         e_impact,
                            "inherent_score": e_like * e_impact,
                            "treatment":      e_treat,
                            "status":         e_status,
                            "control_refs":   [r.strip() for r in e_ctrl.split(",") if r.strip()],
                            "residual_score": e_resid,
                            "notes":          e_notes.strip(),
                        }
                        save_risk_register(data)
                        st.session_state.pop(f"editing_risk_{i}", None)
                        st.rerun()
                with cancel_edit:
                    if st.form_submit_button("Cancel"):
                        st.session_state.pop(f"editing_risk_{i}", None)
                        st.rerun()

        st.markdown('<div style="height:1px;background:var(--border);margin:2px 0;"></div>', unsafe_allow_html=True)
