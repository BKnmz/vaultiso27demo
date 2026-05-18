"""
VaultISO27 — ISO 27001:2022 Document Generator
On-premises · No cloud · Local AI
Run: streamlit run ui/app.py  (from isms-automation/ directory)
"""
import sys
from pathlib import Path

import streamlit as st

# Ensure ui/ is on path so page modules can import core, components, icons
_UI_DIR = Path(__file__).parent
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from core import (
    load_config, completion_stats, get_clause_status,
    CLAUSE_NAMES, OUTPUTS_DIR, __version__,
)
from styles import CSS
from icons import icon


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar(page: str, pending_count: int, cfg: dict) -> None:
    model_name = cfg.get("llm", {}).get("model", "—")

    def nav(pid: str, label: str, icon_name: str) -> str:
        active = "active" if page == pid else ""
        badge = (
            f'<span class="badge">{pending_count}</span>'
            if pid == "review" and pending_count > 0 else ""
        )
        return (
            f'<a href="?page={pid}" target="_self" class="nav-item {active}">'
            f'{icon(icon_name, 16)}<span>{label}</span>{badge}</a>'
        )

    html = f"""
    <div class="sidebar-brand">
      <div class="brand-mark">V</div>
      <div>
        <div class="brand-name">VaultISO27 Demo</div>
        <div class="brand-sub">ISO 27001:2022 · 5-clause edition</div>
      </div>
    </div>
    <div class="nav-label">Main</div>
    {nav("dashboard",  "Dashboard",         "dashboard")}
    {nav("org",        "Organization",       "building")}
    {nav("generate",   "Generate",           "sparkles")}
    {nav("review",     "Review",             "check")}
    {nav("documents",  "Documents",          "folder")}
    <div class="nav-label">Compliance</div>
    {nav("annex",      "Annex A Controls",   "grid")}
    {nav("knowledge",  "Knowledge Base",     "search")}
    <div style="margin-top:auto">
      <div class="sidebar-footer">
        <div class="engine-pill"><span class="dot"></span>Local engine online</div>
        <div style="margin-top:10px;color:var(--ink-3);font-size:11.5px;
                    font-family:var(--font-mono)">{model_name}</div>
        <div style="margin-top:2px;color:var(--ink-4);font-size:11px">
          v{__version__} · Data never leaves this machine.</div>
        <div style="margin-top:14px;padding:10px;background:var(--surface-2);border-radius:var(--radius-sm);
                    font-size:10.5px;color:var(--ink-3);line-height:1.5">
          <strong style="color:var(--ink-2)">Important:</strong> User organisations must obtain
          the original ISO/IEC 27001:2022 standard documents directly from ISO. Generated
          documents are drafts — review against the official standard before certification.
        </div>
      </div>
    </div>
    """
    st.sidebar.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def _route(page: str) -> None:
    from _pages import dashboard, organization, generate, review, documents, annex, knowledge
    pages = {
        "dashboard": dashboard,
        "org":        organization,
        "generate":   generate,
        "review":     review,
        "documents":  documents,
        "annex":      annex,
        "knowledge":  knowledge,
    }
    mod = pages.get(page, dashboard)
    mod.render()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="VaultISO27 Demo",
        page_icon="V",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    try:
        cfg = load_config()
    except Exception:
        cfg = {"llm": {"model": "—"}}

    pending_docs = [
        cid for cid in CLAUSE_NAMES
        if get_clause_status(cid) in ("DRAFT", "REVISION")
        and (OUTPUTS_DIR / f"{cid}.md").exists()
    ]

    page = st.query_params.get("page", "dashboard")
    _render_sidebar(page, len(pending_docs), cfg)
    _route(page)


if __name__ == "__main__":
    main()
