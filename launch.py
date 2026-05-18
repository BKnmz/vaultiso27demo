"""
ISMS Automation Launcher
Checks prerequisites, starts Ollama if not running, launches Streamlit dashboard.
Run: python launch.py
"""

import logging
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent

_LOG_DIR = BASE_DIR / "logs"
_LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(_LOG_DIR / "vaultiso.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("launcher")
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
PORT = 8501


def check_python():
    if sys.version_info < (3, 9):
        log.error("Python 3.9+ required (found %s)", sys.version)
        sys.exit(1)
    log.info("Python %s  OK", sys.version.split()[0])


def check_dependencies():
    missing = []
    for pkg in ["streamlit", "chromadb", "sentence_transformers", "yaml", "jinja2"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        log.error("Missing packages: %s — run install.bat to set up dependencies.", ', '.join(missing))
        sys.exit(1)
    log.info("Dependencies  OK")


def check_hardware_config():
    """Auto-run setup_config.py if timeouts block is missing (first launch or migration)."""
    import yaml
    cfg = yaml.safe_load((BASE_DIR / "config.yaml").read_text())
    if "timeouts" not in cfg:
        log.info("Hardware config not found — running auto-configuration...")
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "setup_config.py")],
            cwd=str(BASE_DIR),
        )
        if result.returncode != 0:
            log.warning("Hardware auto-config failed. Default timeouts will be used.")
        else:
            log.info("Hardware config  OK")


def check_rag_index():
    chroma_path = BASE_DIR / "rag" / "chroma_db"
    if not chroma_path.exists():
        log.info("ChromaDB index not found — building now (internet required for first run)...")
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "rag_setup.py")],
            cwd=str(BASE_DIR),
        )
        if result.returncode != 0:
            log.error("RAG setup failed. Check rag/ISO27001_Audit_Checklist_V3.xlsx exists.")
            sys.exit(1)

    log.info("RAG index  OK")


def check_ollama():
    import requests
    try:
        import yaml
        cfg = yaml.safe_load((BASE_DIR / "config.yaml").read_text())
        base_url = cfg["llm"]["base_url"]
        r = requests.get(f"{base_url}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        log.info("Ollama running  OK  (models: %s)", ', '.join(models) if models else 'none pulled yet')
        if not models:
            log.warning("No models pulled yet. Run: ollama pull phi4-mini:3.8b-q4_K_M")
        else:
            gen_model = cfg.get("llm", {}).get("model", "")
            critic_model = cfg.get("critic", {}).get("model", "")
            for required in [m for m in [gen_model, critic_model] if m]:
                if not any(required in m for m in models):
                    log.warning(
                        "Model '%s' is not pulled. Run: ollama pull %s", required, required
                    )
    except Exception:
        log.warning("Ollama not running — attempting to start...")
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            time.sleep(3)
            log.info("Ollama started  OK")
        except FileNotFoundError:
            log.warning("Ollama not found. Download from: https://ollama.com/download")
            log.warning("The dashboard will open but pipeline won't run until Ollama is installed.")


def launch_streamlit():
    app_path = BASE_DIR / "ui" / "app.py"
    log.info("Launching dashboard at http://localhost:%d ...", PORT)

    cmd = [
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.port", str(PORT),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--theme.base", "light",
    ]

    proc = subprocess.Popen(cmd, cwd=str(BASE_DIR))

    # Wait for Streamlit to be ready then open browser
    time.sleep(3)
    webbrowser.open(f"http://localhost:{PORT}")

    log.info("Dashboard running. Press Ctrl+C to stop.")
    try:
        proc.wait()
    except KeyboardInterrupt:
        log.info("Stopping VaultISO27...")
        proc.terminate()


def _get_version():
    core = BASE_DIR / "ui" / "core.py"
    try:
        for line in core.read_text(encoding="utf-8").splitlines():
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "?"


def main():
    # Lock HuggingFace to offline mode unconditionally — prevents sentence_transformers
    # from making network calls to huggingface.co on every model load (85+ second hang offline)
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"

    log.info("=" * 50)
    log.info("  VaultISO27 v%s — ISO 27001:2022 Document Generator", _get_version())
    log.info("  On-Premises | No Cloud")
    log.info("=" * 50)
    log.info("Checking prerequisites...")

    check_python()
    check_dependencies()
    check_hardware_config()
    check_rag_index()
    check_ollama()
    launch_streamlit()


if __name__ == "__main__":
    main()
