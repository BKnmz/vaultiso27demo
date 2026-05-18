"""Shared render helpers used by all page modules."""
from __future__ import annotations
import streamlit as st
from icons import icon as _icon


def page_head(title: str, sub: str = "", actions_html: str = "") -> None:
    sub_html = f'<p class="page-sub">{sub}</p>' if sub else ""
    actions = f'<div class="page-actions">{actions_html}</div>' if actions_html else ""
    st.markdown(
        f'<div class="page-head">'
        f'<div><h1 class="page-title">{title}</h1>{sub_html}</div>'
        f'{actions}'
        f'</div>',
        unsafe_allow_html=True,
    )


def pill(kind: str, text: str, dot: bool = True) -> str:
    dot_html = '<span class="dot"></span>' if dot else ""
    return f'<span class="pill {kind}">{dot_html}{text}</span>'


def metric_html(label: str, value, unit: str = "", delta: str = "",
                delta_up: bool = False, progress_pct: int = -1) -> str:
    unit_html = f'<span class="unit">{unit}</span>' if unit else ""
    up_cls = " up" if delta_up else ""
    delta_html = f'<div class="metric-delta{up_cls}">{delta}</div>' if delta else ""
    prog_html = (
        f'<div class="progress accent" style="margin-top:10px">'
        f'<div style="width:{progress_pct}%"></div></div>'
    ) if progress_pct >= 0 else ""
    return (
        f'<div class="metric">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}{unit_html}</div>'
        f'{delta_html}{prog_html}</div>'
    )


def metrics_row(items: list[dict]) -> None:
    cols_css = f"repeat({len(items)}, 1fr)"
    inner = "".join(metric_html(**it) for it in items)
    st.markdown(
        f'<div class="metrics-row" style="grid-template-columns:{cols_css}">{inner}</div>',
        unsafe_allow_html=True,
    )


def card_open(title: str = "", actions_html: str = "", flush: bool = False) -> None:
    head = ""
    if title or actions_html:
        actions = f'<div>{actions_html}</div>' if actions_html else ""
        head = (
            f'<div class="card-head">'
            f'<h3 class="card-title">{title}</h3>{actions}'
            f'</div>'
        )
    body_cls = "card-body flush" if flush else "card-body"
    st.markdown(f'<div class="card">{head}<div class="{body_cls}">', unsafe_allow_html=True)


def card_close() -> None:
    st.markdown('</div></div>', unsafe_allow_html=True)


def finding_html(kind: str, title: str, body: str, badge: str = "") -> str:
    badge_html = f'<span class="pill {kind}" style="font-size:11px;padding:1px 6px">{badge}</span>' if badge else ""
    return (
        f'<div class="finding {kind}">'
        f'<div class="f-head"><span class="f-title">{title}</span>{badge_html}</div>'
        f'<div class="f-body">{body}</div>'
        f'</div>'
    )


def meta_row_html(key: str, value: str) -> str:
    return (
        f'<div class="meta-row">'
        f'<span class="k">{key}</span>'
        f'<span class="v mono">{value}</span>'
        f'</div>'
    )


def tbl_open(headers: list[str], widths: list[str] | None = None) -> None:
    ths = ""
    for i, h in enumerate(headers):
        w = f' style="width:{widths[i]}"' if widths and i < len(widths) and widths[i] else ""
        ths += f"<th{w}>{h}</th>"
    st.markdown(
        f'<table class="tbl"><thead><tr>{ths}</tr></thead><tbody>',
        unsafe_allow_html=True,
    )


def tbl_close() -> None:
    st.markdown('</tbody></table>', unsafe_allow_html=True)


def stepper_html(steps: list[dict]) -> str:
    items = ""
    for s in steps:
        state = s.get("state", "pending")
        cls = "done" if state == "done" else ("current" if state == "current" else "")
        if state == "done":
            num_inner = _icon("check2", 14)
        else:
            num_inner = str(s["num"])
        items += (
            f'<div class="step {cls}">'
            f'<div class="step-num">{num_inner}</div>'
            f'<div><div class="step-name">{s["name"]}</div>'
            f'<div class="step-desc">{s.get("desc","")}</div></div>'
            f'</div>'
        )
    return f'<div class="stepper">{items}</div>'
