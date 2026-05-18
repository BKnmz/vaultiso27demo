"""Generate page — run the document pipeline."""
from __future__ import annotations
import sys
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from core import (
    CLAUSE_NAMES, BASE_DIR, load_config, get_ollama_models,
    completion_stats, get_clause_status,
)
from components import page_head
from icons import icon


def _color_log_line(line: str) -> str:
    s = line.rstrip()
    if "[DONE]" in s:
        return f'<div class="ok">{s}</div>'
    if "[REVIEWER] CONDITIONAL PASS" in s or "CONDITIONAL PASS" in s:
        return f'<div class="warn">{s}</div>'
    if "ERROR" in s or "Traceback" in s or "FAIL" in s:
        return f'<div class="err">{s}</div>'
    if s.startswith("[") and "] " in s and ("RAG" in s or "Prompting" in s or "Loading" in s or "Auto-rev" in s):
        return f'<div class="dim">{s}</div>'
    if s.startswith("→") or (s.startswith("[") and "Clause" in s):
        return f'<div>{s}</div>'
    return f'<div class="dim">{s}</div>'


def render() -> None:
    # ── Result popup from previous run ───────────────────────────────────
    if "_gen_result" in st.session_state:
        res = st.session_state.pop("_gen_result")
        if res["ok"]:
            st.toast(res["msg"], icon=None)
            st.success(res["msg"])
        else:
            detail = res.get("detail", "")
            st.error(res["msg"] + (f"\n\n```\n{detail}\n```" if detail else ""))

    cfg = load_config()
    _, counts = completion_stats()
    done_count = counts["APPROVED"]
    total      = len(CLAUSE_NAMES)

    actions = (
        f'<a href="?page=org" target="_self" class="btn ghost">'
        f'{icon("settings", 14)} Engine settings</a>'
    )
    page_head(
        "Generate documents",
        "Step 2 — The AI writes your ISO 27001 documents using the organization profile "
        "and the ISO knowledge base. Typical run takes 20–60 minutes.",
        actions,
    )

    col_left, col_right = st.columns([2, 1])

    with col_left:
        # ── Options card ─────────────────────────────────────────────────
        st.markdown('<div class="card"><div class="card-head"><h3 class="card-title">What to generate</h3></div><div class="card-body">', unsafe_allow_html=True)

        mode_key = "gen_mode"
        if mode_key not in st.session_state:
            st.session_state[mode_key] = "all"

        c1, c2 = st.columns(2)
        with c1:
            all_selected = st.session_state[mode_key] == "all"
            border = "1.5px solid var(--ink)" if all_selected else "1px solid var(--border-2)"
            st.markdown(
                f'<div style="border:{border};border-radius:8px;padding:14px;cursor:pointer">',
                unsafe_allow_html=True,
            )
            if st.button("All 23 documents", key="btn_mode_all", use_container_width=True,
                         type="primary" if all_selected else "secondary",
                         help="The AI writes every required ISO 27001 document using your company info. Takes 20-60 minutes."):
                st.session_state[mode_key] = "all"
                st.rerun()
            st.markdown(
                '<div class="hint" style="text-align:center">Full ISMS — clauses 4.1 through 10.2</div></div>',
                unsafe_allow_html=True,
            )
        with c2:
            one_selected = st.session_state[mode_key] == "one"
            border2 = "1.5px solid var(--ink)" if one_selected else "1px solid var(--border-2)"
            st.markdown(
                f'<div style="border:{border2};border-radius:8px;padding:14px;cursor:pointer">',
                unsafe_allow_html=True,
            )
            if st.button("One specific document", key="btn_mode_one", use_container_width=True,
                         type="primary" if one_selected else "secondary",
                         help="Generate just one clause document. Useful for re-running a single document after editing your profile."):
                st.session_state[mode_key] = "one"
                st.rerun()
            st.markdown(
                '<div class="hint" style="text-align:center">Pick a single clause</div></div>',
                unsafe_allow_html=True,
            )

        cid = None
        if st.session_state[mode_key] == "one":
            cid = st.selectbox(
                "Select document",
                list(CLAUSE_NAMES.keys()),
                format_func=lambda x: f"{x} — {CLAUSE_NAMES[x]}",
                label_visibility="collapsed",
                help="Pick which ISO 27001 clause to generate.",
            )

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        force = st.checkbox(
            "Regenerate from scratch (ignore cached versions)",
            help="Force the AI to rewrite documents even if nothing has changed since the last run.",
        )
        critic_cfg    = cfg.get("critic", {})
        critic_on     = critic_cfg.get("enabled", True)
        auto_clauses  = critic_cfg.get("auto_clauses", ["5.2", "6.1.2", "6.1.3", "9.3"])
        review_label  = (
            f"Auto-review {len(auto_clauses)} document(s) after generation"
            if critic_on else
            "Auto-review disabled (enable in Settings → AI Engine)"
        )
        st.checkbox(
            review_label, value=critic_on, disabled=True,
            help="After each document, a second AI checks it against ISO 27001 requirements and asks the writer to fix any issues automatically.",
        )
        if critic_on and auto_clauses:
            st.markdown(
                f'<div class="hint" style="margin-left:24px">Clauses {" · ".join(auto_clauses)}</div>',
                unsafe_allow_html=True,
            )
        st.markdown('</div></div>', unsafe_allow_html=True)

        # ── Ollama check + Generate button ────────────────────────────────
        _base_url = cfg.get("llm", {}).get("base_url", "http://localhost:11434")
        _models   = get_ollama_models(_base_url)
        if not _models:
            st.error(
                "AI engine not reachable — Ollama is not running or not accessible. "
                "Start it with `ollama serve` and make sure your model is pulled."
            )

        if st.button(
            "Generate documents",
            type="primary",
            disabled=(not _models),
            key="btn_generate",
            help="Start writing your ISO 27001 documents. Keep this window open until it finishes — typical run is 20-60 minutes.",
        ):
            _cid   = cid if st.session_state.get("gen_mode") == "one" else None
            _force = force
            cmd = [sys.executable, str(BASE_DIR / "pipeline.py")]
            if _cid:
                cmd += ["--clause", _cid]
            if _force:
                cmd += ["--force"]

            log_box   = st.empty()
            log_lines: list[str] = []
            st.session_state["_gen_in_progress"] = True

            with st.spinner("Generating documents — do not close this window…"):
                try:
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", cwd=str(BASE_DIR),
                    )
                    for line in proc.stdout:
                        log_lines.append(line.rstrip())
                        colored = "".join(_color_log_line(l) for l in log_lines[-40:])
                        log_box.markdown(
                            f'<div class="console">{colored}</div>',
                            unsafe_allow_html=True,
                        )
                    proc.wait()

                    done_c   = sum(1 for l in log_lines if "[DONE]"   in l)
                    cached_c = sum(1 for l in log_lines if "[CACHED]" in l)

                    if proc.returncode == 0:
                        parts = [f"{done_c} document(s) generated"] if done_c \
                                else ["All documents are up to date"]
                        if cached_c:
                            parts.append(f"{cached_c} unchanged (cached)")
                        msg = ", ".join(parts) + ". Go to Review to approve them."
                        st.session_state["_gen_result"] = {"ok": True, "msg": msg}
                    else:
                        # Detect Ollama connection error specifically
                        all_text = "\n".join(log_lines)
                        if "Cannot connect" in all_text or "ConnectionError" in all_text:
                            msg = "Cannot connect to Ollama. Make sure Ollama is running (`ollama serve`) and the model is pulled."
                        elif "SystemExit" in all_text:
                            msg = "Pipeline stopped unexpectedly. See the log below for details."
                        else:
                            msg = f"Generation stopped with an error (exit code {proc.returncode})."
                        # Show last 15 non-empty lines as detail
                        detail = "\n".join(l for l in log_lines if l.strip())[-1500:]
                        st.session_state["_gen_result"] = {
                            "ok": False, "msg": msg, "detail": detail,
                        }
                except Exception as e:
                    st.session_state["_gen_result"] = {
                        "ok": False, "msg": f"Could not start generation: {e}", "detail": "",
                    }

            st.session_state["_gen_in_progress"] = False
            st.session_state["_gen_log"] = log_lines
            st.rerun()

        # ── Live log card ─────────────────────────────────────────────────
        log_lines_state = st.session_state.get("_gen_log", [])
        log_html = "".join(_color_log_line(l) for l in log_lines_state[-40:]) or \
                   '<div class="dim">Waiting for generation to start…</div>'

        st.markdown(
            f'<div class="card"><div class="card-head">'
            f'<h3 class="card-title">Live log</h3>'
            f'</div><div class="card-body">'
            f'<div class="console" id="gen-console">{log_html}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    with col_right:
        in_progress = st.session_state.get("_gen_in_progress", False)
        pct = int(done_count / total * 100)

        # Progress card
        q_done = done_count
        q_queued = total - done_count
        st.markdown(
            f'<div class="card" style="margin-bottom:16px">'
            f'<div class="card-head"><h3 class="card-title">Progress</h3></div>'
            f'<div class="card-body">'
            f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">'
            f'<span style="font-family:var(--font-display);font-size:32px;font-weight:500;'
            f'letter-spacing:-0.02em">{q_done}</span>'
            f'<span class="muted" style="font-size:13px">of {total} complete</span>'
            f'<span class="spacer"></span>'
            f'</div>'
            f'<div class="progress accent"><div style="width:{pct}%"></div></div>'
            f'<div class="divider"></div>'
            f'<div class="three-col">'
            f'<div><div class="metric-label">Completed</div>'
            f'<div style="font-size:20px;font-weight:600;color:var(--ok)">{counts["APPROVED"]}</div></div>'
            f'<div><div class="metric-label">Draft</div>'
            f'<div style="font-size:20px;font-weight:600;color:var(--accent)">{counts["DRAFT"]}</div></div>'
            f'<div><div class="metric-label">Missing</div>'
            f'<div style="font-size:20px;font-weight:600;color:var(--ink-3)">{counts["MISSING"]}</div></div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )

        # Engine card
        from components import meta_row_html
        gen_model  = cfg.get("llm", {}).get("model", "—")
        rev_model  = cfg.get("critic", {}).get("model", "—")
        base_url   = cfg.get("llm", {}).get("base_url", "localhost:11434")
        temp       = cfg.get("llm", {}).get("temperature", 0.3)
        top_k      = cfg.get("rag", {}).get("top_k", 3)
        rows = (
            meta_row_html("Generator", gen_model) +
            meta_row_html("Reviewer",  rev_model) +
            meta_row_html("Base URL",  base_url) +
            meta_row_html("Temperature", str(temp)) +
            meta_row_html("ISO chunks per doc", str(top_k))
        )
        st.markdown(
            f'<div class="card" style="margin-bottom:16px">'
            f'<div class="card-head"><h3 class="card-title">Engine</h3></div>'
            f'<div class="card-body tight">{rows}</div></div>',
            unsafe_allow_html=True,
        )

        # Queue preview
        queue_clauses = [(cid, name) for cid, name in CLAUSE_NAMES.items()
                         if get_clause_status(cid) != "APPROVED"][:5]
        q_html = ""
        for i, (qcid, qname) in enumerate(queue_clauses):
            next_pill = '<span class="pill info" style="margin-left:auto">Next</span>' if i == 0 else ""
            bg = "background:var(--surface-2);" if i == 0 else ""
            q_html += (
                f'<div style="display:flex;align-items:center;gap:10px;padding:6px 8px;'
                f'border-radius:6px;{bg}">'
                f'<span class="mono muted" style="width:44px;font-size:11.5px">{qcid}</span>'
                f'<span style="flex:1;font-size:12.5px;color:var(--ink)">{qname}</span>'
                f'{next_pill}</div>'
            )
        st.markdown(
            f'<div class="card">'
            f'<div class="card-head"><h3 class="card-title">Queue preview</h3></div>'
            f'<div class="card-body tight">{q_html or "<span class=muted>All documents generated.</span>"}</div></div>',
            unsafe_allow_html=True,
        )

