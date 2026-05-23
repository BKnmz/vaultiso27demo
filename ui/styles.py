"""CSS for VaultISO27 — injected once at app start via st.markdown."""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Streamlit chrome cleanup ── */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
button[kind="header"] { display: none !important; }

/* ── Root tokens ── */
:root {
  --bg:           oklch(0.985 0.004 95);
  --surface:      oklch(1 0 0);
  --surface-2:    oklch(0.975 0.005 95);
  --surface-3:    oklch(0.955 0.007 95);
  --border:       oklch(0.91 0.006 95);
  --border-2:     oklch(0.86 0.008 95);
  --ink:          oklch(0.22 0.015 240);
  --ink-2:        oklch(0.38 0.012 240);
  --ink-3:        oklch(0.55 0.010 240);
  --ink-4:        oklch(0.72 0.008 240);
  --accent:       oklch(0.50 0.12 200);
  --accent-ink:   oklch(0.32 0.10 200);
  --accent-soft:  oklch(0.96 0.025 200);
  --ok:           oklch(0.58 0.12 155);
  --ok-soft:      oklch(0.96 0.030 155);
  --warn:         oklch(0.68 0.12 75);
  --warn-soft:    oklch(0.97 0.035 85);
  --err:          oklch(0.58 0.14 25);
  --err-soft:     oklch(0.97 0.025 25);
  --radius:       10px;
  --radius-sm:    6px;
  --shadow-1:     0 1px 2px rgba(20,30,45,.05), 0 1px 1px rgba(20,30,45,.03);
  --font-ui:      'Inter', system-ui, sans-serif;
  --font-display: 'Inter Tight', 'Inter', system-ui, sans-serif;
  --font-mono:    'JetBrains Mono', ui-monospace, 'SF Mono', monospace;
}

/* ── Page background ── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
  background: var(--bg) !important;
  font-family: var(--font-ui);
  color: var(--ink);
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}

/* ── Content padding ── */
[data-testid="block-container"] {
  padding-top: 28px !important;
  padding-left: 36px !important;
  padding-right: 36px !important;
  max-width: none !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
  min-width: 248px !important;
  max-width: 248px !important;
  padding: 0 !important;
}
section[data-testid="stSidebar"] > div:first-child {
  padding: 0 !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
  padding: 0 !important;
}

/* Sidebar nav HTML elements */
.sidebar-brand {
  display: flex; align-items: center; gap: 10px;
  padding: 18px 16px 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}
.brand-mark {
  width: 30px; height: 30px; border-radius: 8px;
  background: var(--ink); color: var(--surface);
  display: grid; place-items: center;
  font-family: var(--font-display); font-weight: 700; font-size: 14px;
  letter-spacing: -0.02em; flex: none;
}
.brand-name {
  font-family: var(--font-display); font-weight: 600; font-size: 15px;
  letter-spacing: -0.01em; color: var(--ink);
}
.brand-sub { font-size: 11px; color: var(--ink-3); font-weight: 500; margin-top: 1px; }
.demo-badge {
  display: inline-block; font-size: 9px; font-weight: 700; letter-spacing: 0.06em;
  padding: 1px 5px; border-radius: 4px; vertical-align: middle; margin-left: 4px;
  background: oklch(0.55 0.18 250); color: #fff; font-family: var(--font-mono);
}

.nav-label {
  font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--ink-4); font-weight: 600; padding: 10px 16px 4px;
}
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 16px; margin: 1px 8px;
  border-radius: var(--radius-sm);
  font-size: 13.5px; color: var(--ink-2); font-weight: 500;
  text-decoration: none; cursor: pointer;
  transition: background .1s, color .1s;
}
.nav-item:hover { background: var(--surface-2); color: var(--ink); }
.nav-item.active { background: var(--ink); color: var(--surface) !important; }
.nav-item.active svg { stroke: var(--surface); }
.nav-item svg { color: var(--ink-3); width: 16px; height: 16px; flex: none; }
.nav-item .badge {
  margin-left: auto;
  background: var(--warn-soft); color: oklch(0.42 0.12 75);
  font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 999px;
}
.nav-item.active .badge { background: rgba(255,255,255,.18); color: var(--surface); }
.sidebar-footer {
  margin-top: auto; padding: 14px 16px;
  border-top: 1px solid var(--border);
}
.engine-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 8px; border-radius: 999px;
  background: var(--ok-soft); color: oklch(0.38 0.10 155);
  font-size: 11px; font-weight: 600; border: 1px solid oklch(0.85 0.05 155);
}
.engine-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ok); }

/* ── Page header ── */
.page-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 24px; margin-bottom: 24px;
}
.page-title {
  font-family: var(--font-display); font-size: 26px; font-weight: 600;
  letter-spacing: -0.022em; color: var(--ink); margin: 0 0 4px 0;
}
.page-sub { font-size: 13.5px; color: var(--ink-3); margin: 0; max-width: 620px; }
.page-actions { display: flex; gap: 8px; flex: none; align-items: flex-start; }

/* ── Cards ── */
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow-1); margin-bottom: 16px;
}
.card-head {
  padding: 14px 20px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.card-title { font-size: 14px; font-weight: 600; color: var(--ink); margin: 0; }
.card-body { padding: 20px; }
.card-body.tight { padding: 10px 20px; }
.card-body.flush { padding: 0; }

/* ── Metrics ── */
.metrics-row {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px;
}
.metric {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 16px 18px;
}
.metric-label {
  font-size: 11.5px; color: var(--ink-3); text-transform: uppercase;
  letter-spacing: .06em; font-weight: 600;
}
.metric-value {
  font-family: var(--font-display); font-size: 30px; font-weight: 500;
  letter-spacing: -0.02em; color: var(--ink); margin-top: 4px; line-height: 1.1;
  display: flex; align-items: baseline; gap: 8px;
}
.metric-value .unit { font-size: 14px; color: var(--ink-3); font-weight: 500; }
.metric-delta { margin-top: 6px; font-size: 11.5px; color: var(--ink-3); }
.metric-delta.up { color: oklch(0.45 0.10 155); }

/* ── Progress ── */
.progress {
  height: 6px; background: var(--surface-3); border-radius: 99px; overflow: hidden;
}
.progress > div { height: 100%; background: var(--ink); border-radius: 99px; }
.progress.accent > div { background: var(--accent); }

/* ── Pills ── */
.pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px; border-radius: 99px; font-size: 11.5px; font-weight: 550;
  border: 1px solid var(--border-2); background: var(--surface-2); color: var(--ink-2);
}
.pill.ok    { background: var(--ok-soft);   color: oklch(0.38 0.10 155); border-color: oklch(0.85 0.05 155); }
.pill.warn  { background: var(--warn-soft); color: oklch(0.42 0.12 75);  border-color: oklch(0.85 0.06 75); }
.pill.err   { background: var(--err-soft);  color: oklch(0.45 0.14 25);  border-color: oklch(0.85 0.06 25); }
.pill.info  { background: var(--accent-soft); color: var(--accent-ink); border-color: oklch(0.85 0.05 200); }
.pill.neutral { background: var(--surface-2); color: var(--ink-3); }
.pill .dot  { width: 6px; height: 6px; border-radius: 50%; }
.pill.ok   .dot { background: var(--ok); }
.pill.warn .dot { background: var(--warn); }
.pill.err  .dot { background: var(--err); }
.pill.info .dot { background: var(--accent); }
.pill.neutral .dot { background: var(--ink-4); }

/* ── Tables ── */
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th {
  text-align: left; font-weight: 600; color: var(--ink-3);
  font-size: 11.5px; text-transform: uppercase; letter-spacing: .05em;
  padding: 10px 14px; border-bottom: 1px solid var(--border);
  background: var(--surface-2);
}
.tbl td {
  padding: 12px 14px; border-bottom: 1px solid var(--border);
  color: var(--ink-2); vertical-align: middle;
}
.tbl tr:last-child td { border-bottom: none; }
.tbl tr:hover td { background: var(--surface-2); }
.tbl td.name { color: var(--ink); font-weight: 500; }
.tbl .sec { font-family: var(--font-mono); font-size: 11.5px; color: var(--ink-3); }

/* ── Stepper ── */
.stepper {
  display: grid; grid-template-columns: repeat(4, 1fr);
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden; margin-bottom: 20px;
}
.step {
  padding: 16px 18px; display: flex; align-items: center; gap: 12px;
  border-right: 1px solid var(--border);
}
.step:last-child { border-right: none; }
.step-num {
  width: 26px; height: 26px; border-radius: 50%;
  background: var(--surface-3); color: var(--ink-3);
  display: grid; place-items: center; font-size: 12px; font-weight: 600; flex: none;
}
.step.done    .step-num { background: var(--ok);  color: white; }
.step.current .step-num { background: var(--ink); color: white; }
.step-name { font-size: 13px; font-weight: 550; color: var(--ink); }
.step-desc { font-size: 11.5px; color: var(--ink-3); margin-top: 1px; }

/* ── Layouts ── */
.two-col     { display: grid; grid-template-columns: 2fr 1fr;   gap: 20px; }
.two-col-eq  { display: grid; grid-template-columns: 1fr 1fr;   gap: 20px; }
.three-col   { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.stack       { display: flex;  flex-direction: column; gap: 16px; }
.row         { display: flex;  align-items: center; gap: 10px; }
.row.between { justify-content: space-between; }
.spacer      { flex: 1; }
.divider     { height: 1px; background: var(--border); margin: 18px 0; }
.muted       { color: var(--ink-3); }
.mono        { font-family: var(--font-mono); font-size: 12.5px; }

/* ── Review viewer ── */
.doc-viewer { display: grid; grid-template-columns: 1fr 380px; min-height: 600px; }
.doc-body   { padding: 28px 32px; border-right: 1px solid var(--border); overflow: hidden; }
.doc-body h1 {
  font-family: var(--font-display); font-size: 22px; font-weight: 600;
  letter-spacing: -0.02em; margin: 0 0 8px;
}
.doc-body h2 {
  font-family: var(--font-display); font-size: 15px; font-weight: 600;
  margin: 20px 0 8px; color: var(--ink);
}
.doc-body p  { font-size: 13.5px; color: var(--ink-2); line-height: 1.65; margin: 0 0 10px; }
.doc-body ul { padding-left: 20px; margin: 6px 0 10px; }
.doc-body li { font-size: 13.5px; color: var(--ink-2); line-height: 1.6; margin: 3px 0; }
.doc-side { padding: 24px; background: var(--surface-2); }
.meta-row {
  display: flex; justify-content: space-between; font-size: 12.5px;
  padding: 8px 0; border-bottom: 1px solid var(--border);
}
.meta-row:last-child { border-bottom: none; }
.meta-row .k { color: var(--ink-3); }
.meta-row .v { color: var(--ink); font-weight: 550; }

/* ── Findings ── */
.finding {
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 12px 14px; background: var(--surface); margin-bottom: 10px;
}
.finding .f-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.finding .f-title { font-size: 13px; font-weight: 600; color: var(--ink); }
.finding .f-body  { font-size: 12.5px; color: var(--ink-2); line-height: 1.5; }
.finding.warn  { border-left: 3px solid var(--warn); }
.finding.err   { border-left: 3px solid var(--err); }
.finding.ok    { border-left: 3px solid var(--ok); }

/* ── Annex A ── */
.annex-grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 6px; }
.annex-chip {
  aspect-ratio: 1/1; border-radius: 6px; background: var(--surface-3);
  display: grid; place-items: center;
  font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-3);
  border: 1px solid var(--border); cursor: pointer;
}
.annex-chip.impl { background: var(--ok-soft);   color: oklch(0.38 0.10 155); border-color: oklch(0.85 0.05 155); }
.annex-chip.part { background: var(--warn-soft);  color: oklch(0.42 0.12 75);  border-color: oklch(0.85 0.06 75); }
.annex-chip.plan { background: var(--accent-soft); color: var(--accent-ink);   border-color: oklch(0.85 0.05 200); }
.annex-chip.na   { background: var(--surface-2); color: var(--ink-4); }
.annex-chip.selected { outline: 2px solid var(--ink); outline-offset: 1px; }

/* ── Console / log ── */
.console {
  background: oklch(0.18 0.010 240); color: oklch(0.88 0.010 95);
  font-family: var(--font-mono); font-size: 12px; padding: 14px 16px;
  border-radius: var(--radius-sm); line-height: 1.55; max-height: 280px; overflow: auto;
}
.console .ok   { color: oklch(0.75 0.12 155); }
.console .warn { color: oklch(0.75 0.12 75); }
.console .err  { color: oklch(0.72 0.14 25); }
.console .dim  { color: oklch(0.55 0.010 95); }

/* ── Buttons (inline HTML) ── */
.btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 8px 14px; border-radius: var(--radius-sm);
  font-size: 13px; font-weight: 550;
  border: 1px solid var(--border-2); background: var(--surface); color: var(--ink);
  cursor: pointer; font-family: inherit; text-decoration: none;
  transition: background .12s, border-color .12s;
}
.btn:hover { background: var(--surface-2); border-color: var(--ink-4); }
.btn.primary { background: var(--ink); color: var(--surface); border-color: var(--ink); }
.btn.primary:hover { background: oklch(0.16 0.015 240); }
.btn.accent  { background: var(--accent); color: white; border-color: var(--accent); }
.btn.ghost   { background: transparent; border-color: transparent; color: var(--ink-2); }
.btn.ghost:hover { background: var(--surface-2); }
.btn.sm { padding: 5px 10px; font-size: 12px; }
.btn svg { width: 14px; height: 14px; }

/* ── Dropzone ── */
.dropzone {
  border: 1.5px dashed var(--border-2); border-radius: var(--radius);
  padding: 28px; background: var(--surface-2); text-align: center; color: var(--ink-2);
}
.dropzone strong { color: var(--ink); font-weight: 600; }
.icon-big {
  width: 38px; height: 38px; margin: 0 auto 10px;
  display: grid; place-items: center;
  background: var(--surface); border-radius: 10px;
  border: 1px solid var(--border); color: var(--ink-3);
}
.hint { font-size: 11.5px; color: var(--ink-3); margin-top: 4px; }

/* ── Form elements ── */
.label { display: block; font-size: 12px; font-weight: 550; color: var(--ink-2); margin-bottom: 6px; }
.field + .field { margin-top: 14px; }

/* ── Streamlit widget restyling ── */
.stButton button {
  font-family: var(--font-ui) !important;
  border-radius: var(--radius-sm) !important;
  font-weight: 550 !important;
}
div[data-testid="element-container"] { background: transparent !important; }
[data-testid="stDataFrame"] { background: var(--surface); border-radius: var(--radius); }

/* Scrollbars */
* { scrollbar-width: thin; scrollbar-color: var(--border-2) var(--bg); }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 8px; border: 2px solid var(--bg); }
::-webkit-scrollbar-thumb:hover { background: var(--ink-4); }
[data-testid="stMain"] { overflow-y: auto !important; }
</style>
"""
