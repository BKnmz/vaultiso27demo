"""Organization page — profile, personnel, GitHub, AI engine, model guide."""
from __future__ import annotations
import sys
import html as _html
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from core import (
    MANDATORY_ORG_FIELDS, MODEL_GUIDE, CLAUSE_NAMES, ORG_JSON_SCHEMA, get_active_clauses,
    load_org, save_org, load_config, save_config,
    extract_text_from_upload, extract_org_with_llm, extract_personnel_with_llm,
    _parse_asset_register, _parse_supplier_register,
    upload_clause_to_github, get_ollama_models, detect_hardware,
    _field_val,
)
from components import page_head, pill
from icons import icon


def _render_html_table(rows: list[dict], columns: list[str]) -> None:
    """Render rows as the same .tbl HTML used by Dashboard/Documents."""
    if not rows:
        return
    th = "".join(f'<th>{_html.escape(c)}</th>' for c in columns)
    body = ""
    for r in rows:
        tds = "".join(
            f'<td style="font-size:12.5px">{_html.escape(str(r.get(c, "")))}</td>'
            for c in columns
        )
        body += f'<tr>{tds}</tr>'
    st.markdown(
        f'<div class="card"><div class="card-body flush">'
        f'<table class="tbl"><thead><tr>{th}</tr></thead>'
        f'<tbody>{body}</tbody></table></div></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Inner tab routing
# ---------------------------------------------------------------------------

_TABS = ["Profile", "Key personnel", "Asset register", "Supplier register",
         "GitHub", "AI engine", "Model guide"]


def render() -> None:
    page_head(
        "Organization profile",
        "Step 1 — Set up your company profile. The AI reads a document you upload and fills this in automatically.",
    )

    section = st.query_params.get("section", "profile")

    # Pill tab row
    tabs_html = ""
    for t in _TABS:
        tid = t.lower().replace(" ", "_")
        active = "active" if section == tid else ""
        # Use ink background for active, transparent for others
        bg = "background:var(--ink);color:var(--surface)" if active == "active" else "color:var(--ink-2)"
        tabs_html += (
            f'<a href="?page=org&section={tid}" target="_self" style="text-decoration:none">'
            f'<div style="padding:8px 14px;border-radius:6px;font-size:13px;font-weight:550;'
            f'cursor:pointer;{bg}">{t}</div></a>'
        )
    st.markdown(
        f'<div class="card" style="margin-bottom:20px">'
        f'<div style="display:flex;gap:4px;padding:6px;border-bottom:1px solid var(--border);'
        f'flex-wrap:wrap">{tabs_html}</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="card-body">', unsafe_allow_html=True)

    if section == "profile":
        _tab_profile()
    elif section == "key_personnel":
        _tab_personnel()
    elif section == "asset_register":
        _tab_asset_register()
    elif section == "supplier_register":
        _tab_supplier_register()
    elif section == "github":
        _tab_github()
    elif section == "ai_engine":
        _tab_ai_engine()
    elif section == "model_guide":
        _tab_model_guide()
    else:
        _tab_profile()

    st.markdown('</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Profile tab
# ---------------------------------------------------------------------------

def _tab_profile() -> None:
    org = load_org()
    cfg = load_config()

    # AI extraction result banner
    if "extracted_org" in st.session_state:
        extracted = st.session_state["extracted_org"]
        found   = [(k, lbl) for k, lbl in MANDATORY_ORG_FIELDS if _field_val(extracted.get(k, ""))]
        missing = [(k, lbl) for k, lbl in MANDATORY_ORG_FIELDS if not _field_val(extracted.get(k, ""))]
        banner_text = (
            f"AI found {len(found)} of {len(MANDATORY_ORG_FIELDS)} required fields"
            + (f" — {len(missing)} left to fill in manually" if missing else " — all fields found!")
        )
        st.markdown(
            f'<div style="background:var(--accent-soft);border:1px solid oklch(0.85 0.05 200);'
            f'border-radius:var(--radius);padding:14px 16px;display:flex;align-items:flex-start;'
            f'gap:12px;margin-bottom:20px">'
            f'<div style="width:32px;height:32px;border-radius:8px;background:var(--surface);'
            f'color:var(--accent-ink);display:grid;place-items:center;flex:none;'
            f'border:1px solid oklch(0.85 0.05 200)">{icon("sparkles",16)}</div>'
            f'<div style="flex:1"><div style="font-weight:600;color:var(--accent-ink);font-size:13.5px">'
            f'{banner_text}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        col_left, col_right = st.columns(2)

        with col_left:
            if found:
                rows_html = ""
                for k, lbl in found:
                    val = extracted.get(k, "")
                    display = ", ".join(val) if isinstance(val, list) else str(val)
                    rows_html += (
                        f'<div style="display:grid;grid-template-columns:160px 1fr auto;'
                        f'gap:16px;align-items:center;padding:14px 20px;'
                        f'border-bottom:1px solid var(--border)">'
                        f'<div style="font-size:12px;color:var(--ink-3);font-weight:550">{lbl}</div>'
                        f'<div style="font-size:13px;color:var(--ink)">{display[:120]}</div>'
                        f'{icon("check2",14)}'
                        f'</div>'
                    )
                st.markdown(
                    f'<div class="card" style="margin-bottom:16px">'
                    f'<div class="card-head"><h3 class="card-title">Fields found</h3>'
                    f'{pill("ok", f"{len(found)} / {len(MANDATORY_ORG_FIELDS)}")}</div>'
                    f'<div class="card-body flush">{rows_html}</div></div>',
                    unsafe_allow_html=True,
                )

            if missing:
                patch = {}
                st.markdown(
                    f'<div class="card"><div class="card-head">'
                    f'<h3 class="card-title">Fields to complete</h3>'
                    f'{pill("warn", f"{len(missing)} remaining")}</div>'
                    f'<div class="card-body">',
                    unsafe_allow_html=True,
                )
                for k, lbl in missing:
                    patch[k] = st.text_input(lbl, key=f"patch_{k}",
                                             placeholder=f"Enter {lbl.lower()} manually")
                st.markdown('</div></div>', unsafe_allow_html=True)

                if st.button("Save Organization Profile", type="primary", use_container_width=True):
                    final = {**org, **extracted}
                    for k, _ in missing:
                        v = patch.get(k, "")
                        if v.strip():
                            if isinstance(ORG_JSON_SCHEMA.get(k), list):
                                final[k] = [x.strip() for x in v.split(",") if x.strip()]
                            else:
                                final[k] = v.strip()
                    save_org(final)
                    st.session_state.pop("extracted_org", None)
                    st.success("Organization profile saved.")
                    st.rerun()

        with col_right:
            _upload_card(org, cfg)

    else:
        col_left, col_right = st.columns(2)
        with col_left:
            _manual_form_card(org)
        with col_right:
            _upload_card(org, cfg)


def _manual_form_card(org: dict) -> None:
    """Manual entry form — always visible, pre-populated from existing profile."""
    has_profile = bool(org.get("name", "").strip())
    title = "Edit organization profile" if has_profile else "Fill in manually"
    badge = pill("ok", org["name"][:30], dot=False) if has_profile else ""

    st.markdown(
        f'<div class="card" style="margin-bottom:16px">'
        f'<div class="card-head"><h3 class="card-title">{title}</h3>{badge}</div>'
        f'<div class="card-body">',
        unsafe_allow_html=True,
    )

    def _list_val(v) -> str:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v) if v else ""

    name     = st.text_input("Company name *", value=org.get("name", ""), key="mf_name",
                              help="Legal name of the organization. Required.")
    industry = st.text_input("Industry / sector", value=org.get("industry", ""), key="mf_industry",
                              help="e.g. Software, Healthcare, Financial Services")
    size     = st.text_input("Number of employees", value=org.get("size", ""), key="mf_size",
                              placeholder="e.g. 45 employees",
                              help="Approximate headcount — used in scope statement.")
    scope    = st.text_area("What the company does (ISMS scope)", value=org.get("scope", ""),
                             key="mf_scope", height=80,
                             placeholder="1–2 sentences: core business + IT activities in scope",
                             help="This becomes the ISMS scope statement for Clause 4.3.")
    locations = st.text_input("Where the company operates", value=_list_val(org.get("locations")),
                               key="mf_locations", placeholder="e.g. Berlin, London, Remote",
                               help="Comma-separated list of offices or operating regions.")
    processes = st.text_input("Main services or products", value=_list_val(org.get("primary_processes")),
                               key="mf_processes", placeholder="e.g. SaaS platform, Data analytics, Consulting",
                               help="Comma-separated list of core business activities.")
    depts    = st.text_input("Departments / teams", value=_list_val(org.get("departments")),
                              key="mf_depts", placeholder="e.g. R&D, Sales, IT, HR",
                              help="Comma-separated list of internal teams in scope.")
    regs     = st.text_input("Data privacy & regulatory drivers", value=_list_val(org.get("regulatory_drivers") or org.get("legal_basis")),
                              key="mf_regs", placeholder="e.g. GDPR, NIS2, ISO 27001, TISAX",
                              help="Comma-separated regulations or standards the company must comply with.")
    controls = st.text_input("Existing security measures", value=_list_val(org.get("existing_controls")),
                              key="mf_controls", placeholder="e.g. MFA, VPN, Antivirus, Firewall",
                              help="Comma-separated security controls already in place.")

    st.markdown(
        '<div class="hint" style="margin-top:8px">Fields marked * are required. '
        'All changes save to <code>inputs/organization_data.json</code> — never sent to the cloud.</div>',
        unsafe_allow_html=True,
    )
    st.markdown('</div></div>', unsafe_allow_html=True)

    # Persist save feedback across rerun
    if st.session_state.get("_org_saved"):
        st.success(
            "Organization profile saved. "
            "Next: add **Key Personnel** (managers, CISO, DPO) in the tab above — "
            "they appear in document headers and review sign-offs."
        )
        st.session_state.pop("_org_saved", None)

    if st.button("Save Organization Profile", type="primary", key="btn_manual_save",
                 use_container_width=True,
                 help="Save these details. You can come back and edit at any time."):
        if not name.strip():
            st.error("Company name is required.")
        else:
            def _parse_list(raw: str) -> list:
                return [x.strip() for x in raw.split(",") if x.strip()]

            form_data = {
                "name":              name.strip(),
                "industry":          industry.strip(),
                "size":              size.strip(),
                "scope":             scope.strip(),
                "locations":         _parse_list(locations),
                "primary_processes": _parse_list(processes),
                "departments":       _parse_list(depts),
                "regulatory_drivers": _parse_list(regs),
                "legal_basis":       _parse_list(regs),
                "existing_controls": _parse_list(controls),
            }
            final = {**load_org(), **form_data}
            save_org(final)
            st.session_state["_org_saved"] = True
            st.rerun()


def _upload_card(org: dict, cfg: dict) -> None:
    """Upload + extract card (right column of Profile tab)."""
    st.markdown(
        f'<div class="card" style="margin-bottom:16px">'
        f'<div class="card-head"><h3 class="card-title">Upload source document</h3></div>'
        f'<div class="card-body">',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="dropzone">'
        f'<div class="icon-big">{icon("upload",18)}</div>'
        f'<div><strong>Drop a document</strong> or click to browse</div>'
        f'<div class="hint" style="margin-top:4px">PDF · Word (.docx) · plain text · under 5 MB</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader(
        "Upload company document",
        type=["pdf", "docx", "txt", "md", "html", "htm"],
        label_visibility="collapsed",
        help="Drop a PDF, Word (.docx), plain-text, or HTML file describing your company. The AI reads it and fills in your profile automatically.",
    )

    if uploaded_file:
        if uploaded_file.size > 5 * 1024 * 1024:
            st.warning("Large file detected — only the first 5,000 words will be used.")
        if st.button("Extract with AI", type="primary", key="btn_extract"):
            with st.status("Analyzing your document…", expanded=True) as status:
                status.write("Reading document…")
                text = extract_text_from_upload(uploaded_file)
                if text:
                    status.write(
                        f"Document read ({len(text.split())} words). "
                        "AI is identifying your organization details — this takes 1–3 minutes. Please wait."
                    )
                    extracted = extract_org_with_llm(text, cfg)
                    if extracted:
                        st.session_state["extracted_org"] = extracted
                        status.update(label="Extraction complete.", state="complete")
                        st.rerun()
                    else:
                        status.update(label="Extraction failed.", state="error")
                else:
                    status.update(label="Could not read the file.", state="error")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:12px;font-weight:550;color:var(--ink-2);margin-bottom:8px">'
        'For best results, the document should mention:</div>'
        '<ul style="margin:0;padding-left:18px;font-size:12.5px;color:var(--ink-2);line-height:1.7">'
        '<li>Company name &amp; industry</li>'
        '<li>Number of employees</li>'
        '<li>Main services or products</li>'
        '<li>Where the company operates</li>'
        '<li>Data-privacy laws it must follow</li>'
        '<li>Existing security measures</li>'
        '</ul>',
        unsafe_allow_html=True,
    )
    st.markdown('</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Key Personnel tab
# ---------------------------------------------------------------------------

_UNNAMED_PATTERNS = {"unnamed", "unknown", "tbd", "n/a", "na", "", "-", "—"}

def _kp_is_valid(p: dict) -> bool:
    name = p.get("name", "").strip()
    if not name:
        return False
    # Strip surrounding parentheses/brackets then check against placeholder words
    clean = name.strip("()[]").lower()
    return clean not in _UNNAMED_PATTERNS and not clean.startswith("unnamed")


def _tab_personnel() -> None:
    org = load_org()
    cfg = load_config()
    current = org.get("key_personnel", [])

    # Persist save feedback across rerun
    if st.session_state.get("_kp_saved"):
        n = st.session_state.pop("_kp_saved")
        st.success(f"Saved {n} person(s) to `inputs/organization_data.json`.")

    if current:
        st.markdown(
            '<div class="hint" style="margin-bottom:8px">Edit roles or names inline, then click '
            '<strong>Save changes</strong> to apply.</div>',
            unsafe_allow_html=True,
        )
        for i, p in enumerate(current):
            c1, c2, c3 = st.columns([3, 4, 1])
            with c1:
                st.text_input("Role", value=p.get("role", ""), key=f"kp_role_{i}",
                              label_visibility="collapsed" if i > 0 else "visible")
            with c2:
                st.text_input("Name", value=p.get("name", ""), key=f"kp_name_{i}",
                              label_visibility="collapsed" if i > 0 else "visible")
            with c3:
                st.write("")
                if st.button("Remove", key=f"kp_del_{i}"):
                    current.pop(i)
                    org["key_personnel"] = current
                    save_org(org)
                    st.session_state["_kp_saved"] = 0
                    st.rerun()

        if st.button("Save changes", key="kp_save_edits", type="primary"):
            updated = []
            for i in range(len(current)):
                role = st.session_state.get(f"kp_role_{i}", "").strip()
                name = st.session_state.get(f"kp_name_{i}", "").strip()
                if role and name:
                    updated.append({"role": role, "name": name})
            org["key_personnel"] = updated
            save_org(org)
            st.session_state["_kp_saved"] = len(updated)
            st.rerun()
    else:
        st.info("No key personnel saved yet. Add manually or extract from an org chart below.")

    with st.expander("Add a person manually"):
        mc1, mc2 = st.columns(2)
        new_role = mc1.text_input("Role (e.g. CISO, CEO)", key="kp_new_role")
        new_name = mc2.text_input("Full name", key="kp_new_name")
        if st.button("Add", key="kp_add_btn"):
            if new_role.strip() and new_name.strip():
                current.append({"role": new_role.strip(), "name": new_name.strip()})
                org["key_personnel"] = current
                save_org(org)
                st.session_state["_kp_saved"] = len(current)
                st.rerun()
            else:
                st.warning("Both role and name are required.")

    st.divider()
    st.markdown("**Extract from Org Chart or Document**")
    st.caption("Upload an org chart, HR document, or any file listing employee names and roles.")

    if kp_file := st.file_uploader("Upload org chart or HR document",
                                    type=["pdf", "docx", "txt", "md", "html", "htm"], key="kp_upload"):
        if st.button("Extract names and roles", key="kp_extract_btn", type="primary"):
            with st.spinner("Extracting names from document…"):
                text = extract_text_from_upload(kp_file)
                if text:
                    extracted_kp = extract_personnel_with_llm(text, cfg)
                    if extracted_kp is not None:
                        # Filter unnamed/placeholder entries in code — not just LLM rules
                        valid = [p for p in extracted_kp if _kp_is_valid(p)]
                        st.session_state["extracted_kp"] = valid

    if "extracted_kp" in st.session_state:
        extracted_kp = st.session_state["extracted_kp"]
        if extracted_kp:
            st.success(f"Found {len(extracted_kp)} person(s) — review and save:")
            for p in extracted_kp:
                st.markdown(f"- **{p.get('name','')}** — {p.get('role','')}")
            if st.button("Save extracted personnel", type="primary", key="kp_save_btn"):
                existing_names = {p.get("name","").lower() for p in current}
                added = 0
                for p in extracted_kp:
                    if p.get("name","").lower() not in existing_names:
                        current.append(p)
                        added += 1
                org["key_personnel"] = current
                save_org(org)
                st.session_state.pop("extracted_kp", None)
                st.session_state["_kp_saved"] = added
                st.rerun()
        else:
            st.warning("No named personnel found in the document. Try a different file or add manually.")
            st.session_state.pop("extracted_kp", None)


# ---------------------------------------------------------------------------
# Asset Register tab
# ---------------------------------------------------------------------------

def _tab_asset_register() -> None:
    org = load_org()
    st.caption(
        "Upload your Asset Register spreadsheet to populate asset data used in risk and "
        "operational documents. Supports the standard Asset Register format "
        "(sheet named 'AssetList' with columns: Asset No, Name, Type, Responsible, "
        "Data Classification, Risk Score)."
    )
    if org.get("assets"):
        st.markdown(f"**{len(org['assets'])} saved assets** — edit inline, delete rows with the × button, or add rows. Click Save to apply.")
        rows_edit = [
            {
                "Asset No":       str(a.get("asset_no", "")),
                "Name":           str(a.get("name") or a.get("system", "")),
                "Type":           str(a.get("type", "")),
                "Classification": str(a.get("data_classification") or a.get("classification", "")),
                "Responsible":    str(a.get("responsible") or a.get("owner", "")),
                "Risk Score":     str(a.get("risk_score", "")),
            }
            for a in org["assets"]
        ]
        edited_df = st.data_editor(
            pd.DataFrame(rows_edit),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="asset_register_editor",
        )
        if st.button("Save changes", key="save_assets_edit", type="primary"):
            updated = [
                {
                    "asset_no":            str(r.get("Asset No", "")),
                    "name":                str(r.get("Name", "")),
                    "type":                str(r.get("Type", "")),
                    "data_classification": str(r.get("Classification", "")),
                    "responsible":         str(r.get("Responsible", "")),
                    "risk_score":          str(r.get("Risk Score", "")),
                }
                for _, r in edited_df.iterrows()
                if str(r.get("Name", "")).strip()
            ]
            org["assets"] = updated
            save_org(org)
            st.success(f"Saved {len(updated)} assets.")
            st.rerun()
        st.divider()

    asset_file = st.file_uploader(
        "Upload Asset Register (.xlsx)", type=["xlsx"], key="asset_register_upload",
        help="Excel file listing your IT assets, owners and classifications. Used to make risk and operational documents specific to your company.",
    )
    if asset_file:
        try:
            parsed_assets = _parse_asset_register(asset_file.read())
            if parsed_assets:
                st.success(f"Found {len(parsed_assets)} assets in the spreadsheet.")
                preview_rows = [
                    {
                        "Asset No":       str(a.get("asset_no", "")),
                        "Name":           str(a.get("name", "")),
                        "Type":           str(a.get("type", "")),
                        "Classification": str(a.get("data_classification", "")),
                        "Responsible":    str(a.get("responsible", "")),
                        "Risk Score":     str(a.get("risk_score", "")),
                    }
                    for a in parsed_assets
                ]
                _render_html_table(
                    preview_rows,
                    ["Asset No", "Name", "Type", "Classification", "Responsible", "Risk Score"],
                )
                if st.button("Save Asset Register", key="save_assets", type="primary"):
                    org_save = load_org()
                    org_save["assets"] = parsed_assets
                    save_org(org_save)
                    st.success(f"Saved {len(parsed_assets)} assets.")
                    st.rerun()
            else:
                st.warning("No assets detected. Check that the file has a sheet with asset rows and a header.")
        except Exception as _ae:
            st.error(f"Could not parse Asset Register: {_ae}")


# ---------------------------------------------------------------------------
# Supplier Register tab
# ---------------------------------------------------------------------------

def _tab_supplier_register() -> None:
    org = load_org()
    st.caption(
        "Upload your Supplier or Risk Evaluation spreadsheet to add supplier risk data "
        "used in Annex A control documentation."
    )
    if org.get("suppliers"):
        with st.expander(f"Currently saved: {len(org['suppliers'])} supplier relationships — click to view"):
            rows_sup = [
                {
                    "Asset":          str(s.get("asset", "—")),
                    "Provider":       "Yes" if s.get("provider_involved") else "No",
                    "Services":       str(s.get("services", "—"))[:60],
                    "Dependency":     str(s.get("dependency_level", "—")),
                    "Classification": str(s.get("data_classification", "—")),
                }
                for s in org["suppliers"]
            ]
            _render_html_table(
                rows_sup,
                ["Asset", "Provider", "Services", "Dependency", "Classification"],
            )

    supplier_file = st.file_uploader(
        "Upload Supplier Register (.xlsx)", type=["xlsx"], key="supplier_register_upload",
        help="Excel file listing your suppliers and their access to data. Used to write supplier-related Annex A controls.",
    )
    if supplier_file:
        try:
            parsed_suppliers = _parse_supplier_register(supplier_file.read())
            if parsed_suppliers:
                st.success(f"Found {len(parsed_suppliers)} supplier relationships.")
                preview_rows = [
                    {
                        "Asset":          str(s.get("asset", "")),
                        "Provider":       "Yes" if s.get("provider_involved") else "No",
                        "Services":       str(s.get("services", ""))[:60],
                        "Dependency":     str(s.get("dependency_level", "")),
                        "Classification": str(s.get("data_classification", "")),
                    }
                    for s in parsed_suppliers
                ]
                _render_html_table(
                    preview_rows,
                    ["Asset", "Provider", "Services", "Dependency", "Classification"],
                )
                if st.button("Save Supplier Register", key="save_suppliers", type="primary"):
                    org_save = load_org()
                    org_save["suppliers"] = parsed_suppliers
                    save_org(org_save)
                    st.success(f"Saved {len(parsed_suppliers)} supplier relationships.")
                    st.rerun()
            else:
                st.warning("No supplier data detected.")
        except Exception as _se:
            st.error(f"Could not parse Supplier Register: {_se}")


# ---------------------------------------------------------------------------
# GitHub tab
# ---------------------------------------------------------------------------

def _tab_github() -> None:
    cfg = load_config()
    gh_cfg = cfg.get("github", {})

    st.info(
        "Your GitHub Personal Access Token (PAT) is stored only in `config.yaml` on this machine. "
        "It is never sent to the AI engine. Use a fine-grained token with "
        "**Contents: Read and Write** permission scoped to a single private repository."
    )

    with st.expander("How to create a GitHub Personal Access Token"):
        st.markdown("""
**Steps to generate a PAT (classic):**
1. Go to **GitHub → Settings** (top-right avatar menu)
2. Scroll to **Developer settings** → **Personal access tokens** → **Tokens (classic)**
3. Click **Generate new token (classic)**
4. Set an expiration date and add a note (e.g. "VaultISO27")
5. Select scopes:
   - **`repo`** — full repository access (required for private repos)
   - **`public_repo`** — only if your target repository is public
6. Click **Generate token** and copy it immediately (it won't be shown again)
7. Paste it into the field below and save

**Target repository format:** `owner/repository-name`
Example: `mycompany/isms-documents`
        """)

    gh_token  = st.text_input(
        "Personal Access Token", value=gh_cfg.get("token",""),
        type="password",
        help="GitHub Personal Access Token with 'repo' scope. Generate one at github.com/settings/tokens.",
    )
    gh_repo   = st.text_input(
        "Repository (owner/repo)", value=gh_cfg.get("repo",""),
        placeholder="e.g. mycompany/isms-documents",
        help="Target GitHub repository. Format: owner/repository-name.",
    )
    gh_folder = st.text_input(
        "Target folder in repo", value=gh_cfg.get("folder","isms-docs/"),
        help="Folder inside the repo where ISO documents will be uploaded. Will be created if it does not exist.",
    )

    if st.button("Save GitHub settings", type="primary", key="gh_save"):
        if "github" not in cfg:
            cfg["github"] = {}
        cfg["github"]["token"]  = gh_token
        cfg["github"]["repo"]   = gh_repo
        cfg["github"]["folder"] = gh_folder
        save_config(cfg)
        st.success("GitHub settings saved.")

    if gh_token and gh_repo:
        if st.button("Test connection", key="gh_test"):
            try:
                from github import Github
                g = Github(gh_token)
                repo_obj = g.get_repo(gh_repo)
                st.success(f"Connected to `{repo_obj.full_name}` ({'private' if repo_obj.private else 'public'})")
            except Exception as e:
                st.error(f"Connection failed: {e}")


# ---------------------------------------------------------------------------
# AI Engine tab
# ---------------------------------------------------------------------------

def _tab_ai_engine() -> None:
    cfg = load_config()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="card"><div class="card-head"><h3 class="card-title">Document generator</h3></div><div class="card-body">', unsafe_allow_html=True)
        base_url  = st.text_input(
            "AI Engine URL", value=cfg["llm"]["base_url"],
            help="Where Ollama is running. Default is http://localhost:11434 — only change if Ollama runs on a different machine.",
        )
        available = get_ollama_models(base_url)
        if available:
            st.success(f"AI engine is running  ·  {len(available)} model(s) installed")
            idx = available.index(cfg["llm"]["model"]) if cfg["llm"]["model"] in available else 0
            selected_model = st.selectbox(
                "Generation model", available, index=idx, key="gen_model_sel",
                help="The AI that writes your ISO 27001 documents. Larger models give better wording but run slower.",
            )
        else:
            st.error("AI engine not reachable. Make sure Ollama is running.")
            selected_model = st.text_input("Model name (manual)", value=cfg["llm"]["model"], key="gen_model_manual")
        temperature = st.slider(
            "Creativity level", 0.0, 1.0, float(cfg["llm"]["temperature"]), 0.05,
            help="Higher = more varied wording. Keep low (0.2-0.3) for compliance text.",
        )
        top_k = st.number_input(
            "ISO reference chunks per document", 1, 10, int(cfg["rag"]["top_k"]),
            help="How many ISO 27001 reference snippets the AI sees per document. More = more accurate but slower.",
        )
        st.markdown('</div></div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card"><div class="card-head"><h3 class="card-title">AI reviewer</h3></div><div class="card-body">', unsafe_allow_html=True)
        critic_cfg     = cfg.get("critic", {})
        critic_enabled = st.toggle(
            "Enable AI Reviewer", value=critic_cfg.get("enabled", True),
            help="Turn on to have a second AI check every generated document against ISO 27001 and ask the writer to fix problems automatically.",
        )
        if available:
            cidx         = available.index(critic_cfg.get("model","")) if critic_cfg.get("model","") in available else 0
            critic_model = st.selectbox(
                "Reviewer model", available, index=cidx, key="rev_model_sel",
                help="The AI that critiques the documents. A small fast model is fine here.",
            )
        else:
            critic_model = st.text_input("Reviewer model name", value=critic_cfg.get("model","qwen2.5:1.5b"), key="rev_model_manual")
        st.caption("Recommended: qwen2.5:1.5b — fastest, fits in GPU memory")
        max_rev = st.number_input(
            "Maximum auto-revision attempts", 0, 5,
            int(critic_cfg.get("max_revisions", 2)),
            help="How many times the writer is allowed to fix the document after reviewer feedback. 2 is usually enough.",
        )
        _active = get_active_clauses()
        _default_auto = [c for c in critic_cfg.get("auto_clauses", ["5.2","6.1.2","6.1.3","9.3"]) if c in _active]
        auto_cl = st.multiselect(
            "Auto-review these documents after generation",
            list(_active.keys()),
            default=_default_auto,
            format_func=lambda x: f"{x} — {CLAUSE_NAMES[x]}",
            help="Pick which documents the reviewer should auto-check. Defaults to the high-stakes clauses.",
        )
        st.markdown('</div></div>', unsafe_allow_html=True)

    # Hardware tier info
    timeouts = cfg.get("timeouts", {})
    tier_name = timeouts.get("hardware_tier", "unknown")
    t_gen  = timeouts.get("ollama_generate", 600)
    t_swap = timeouts.get("model_swap_delay", 12)
    det_ram  = timeouts.get("detected_ram_gb", "?")
    det_vram = timeouts.get("detected_vram_gb", "?")
    st.caption(
        f"Hardware tier: **{tier_name}** ({det_ram} GB RAM · {det_vram} GB VRAM) — "
        f"generation timeout: {t_gen}s · model-swap delay: {t_swap}s"
    )
    col_save, col_redetect = st.columns([2, 1])
    with col_save:
        save_btn = st.button("Save AI engine settings", type="primary")
    with col_redetect:
        if st.button("Re-detect hardware", key="redetect_hw"):
            import subprocess, sys
            from core import BASE_DIR as _BD
            subprocess.run([sys.executable, str(_BD / "setup_config.py")], cwd=str(_BD))
            st.success("Hardware re-detected. Reload page to see updated settings.")
            st.rerun()

    if save_btn:
        cfg["llm"]["base_url"]    = base_url
        cfg["llm"]["model"]       = selected_model
        cfg["llm"]["temperature"] = temperature
        cfg["rag"]["top_k"]       = top_k
        cfg["critic"] = {
            "enabled": critic_enabled, "model": critic_model,
            "temperature": 0.1, "max_revisions": max_rev, "auto_clauses": auto_cl,
        }
        save_config(cfg)
        st.success("Settings saved.")


# ---------------------------------------------------------------------------
# Model Guide tab
# ---------------------------------------------------------------------------

def _tab_model_guide() -> None:
    cfg = load_config()
    hw = detect_hardware()
    ram = hw["ram_gb"]
    vram = hw["vram_gb"]
    cpu = hw["cpu"]
    hw_line = f"{cpu} · {ram} GB RAM" + (f" · {vram} GB VRAM" if vram else " · No NVIDIA GPU detected")

    # Use hardware_tier from setup_config.py if available; else derive from live detection
    tier = cfg.get("timeouts", {}).get("hardware_tier", "")
    if not tier:
        if ram >= 32 and vram >= 8:   tier = "high"
        elif ram >= 16 and vram >= 4: tier = "mid"
        elif ram >= 8:                tier = "low"
        else:                          tier = "minimal"

    tier_labels = {"high": "High-end", "mid": "Mid-range", "low": "Standard", "minimal": "Minimal"}
    st.info(
        f"**Detected hardware:** {hw_line}  \n"
        f"**Tier:** {tier_labels.get(tier, tier)} — models highlighted in teal are recommended for your machine."
    )

    col_redetect, _ = st.columns([1, 3])
    with col_redetect:
        if st.button("Re-detect hardware", key="redetect_hw_guide"):
            import subprocess as _sp
            from core import BASE_DIR as _BD
            _sp.run([sys.executable, str(_BD / "setup_config.py")], cwd=str(_BD))
            st.success("Hardware re-detected. Reload to see updated settings.")
            detect_hardware.clear()
            st.rerun()

    cards_html = ""
    for m in MODEL_GUIDE:
        recommended = tier in m.get("tiers", [])
        border = "border:2px solid var(--accent);" if recommended else ""
        badge = (
            "&nbsp;&nbsp;<span style='font-size:10px;background:var(--accent);color:white;"
            "border-radius:4px;padding:1px 6px'>recommended</span>"
        ) if recommended else ""
        cards_html += (
            f'<div class="card" style="padding:0;{border}">'
            f'<div class="card-body">'
            f'<div class="mono" style="font-size:13px;font-weight:500;color:var(--ink)">'
            f'{m["Model"]}{badge}</div>'
            f'<div style="font-size:12px;color:var(--ink-3);margin:4px 0 12px">{m["Best for"]}</div>'
            f'<div class="meta-row"><span class="k">VRAM</span><span class="v mono">{m["VRAM"]}</span></div>'
            f'<div class="meta-row"><span class="k">Speed</span><span class="v mono">{m["Speed"]}</span></div>'
            f'<div style="margin-top:12px;background:var(--surface-3);border-radius:6px;'
            f'padding:8px 10px;font-family:var(--font-mono);font-size:11.5px;color:var(--ink-2)">'
            f'{m["Install"]}</div>'
            f'</div></div>'
        )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:16px">{cards_html}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("""
**How to install** — open a terminal and run the install command shown in the card.

**Important rules for limited GPU memory (2 GB):**
- Only one model can run at a time
- Ollama switches models automatically, but it adds ~10 seconds per switch
- For machines with 8 GB+ VRAM, use mistral:7b for significantly better document quality

**Offline operation:** After first setup, VaultISO27 runs 100% offline — no internet connection needed.
    """)
