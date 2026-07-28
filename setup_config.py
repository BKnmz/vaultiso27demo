"""
VaultISO27 - Hardware detection and config auto-configuration.
Run once during install (called by install.bat after packages are installed).
Detects RAM, VRAM, CPU; selects appropriate hardware tier; writes defaults
to config.yaml so timeouts/models/num_gpu are calibrated for this machine.

Console strings are ASCII-only on purpose: install.bat runs in a cp1252 console
that cannot print Unicode arrows/box-drawing without crashing.
"""
import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

import requests
import yaml

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
_CATALOG_PATH = BASE_DIR / "models_catalog.json"
_ONLINE_CACHE_PATH = BASE_DIR / "models_catalog.online_cache.json"

# ---------------------------------------------------------------------------
# Hardware tiers - ordered best to worst, first match wins (see select_tier).
#
# Rule: VRAM-fit first. A model only earns a GPU tier if it FITS that card's
# VRAM; a model spilled to CPU runs 5-10x slower, so low-VRAM machines get a
# small fast generator - never a big spilling one. RAM alone never qualifies
# for a big model (32 GB RAM + no GPU still generates at CPU speed).
#
# Model identity (gen_model/reviewer_model/label/why/speed) lives in
# models_catalog.json, a bundled+versioned JSON file — this keeps the model
# picks maintainer-updatable without touching this module. Hardware-tuning
# fields below (thresholds, timeouts, output length) stay in Python since
# they're install-time behavior decisions tightly coupled to this codebase,
# not model facts.
# ---------------------------------------------------------------------------
_TIER_TUNING = [
    {
        "name":              "high",
        "min_ram_gb":        0,
        "min_vram_gb":       12,
        "ollama_timeout":    120,
        "model_swap_delay":  2,
        "num_gpu":           1,
        "num_predict":       2000,
        "length_profile":    "comprehensive (~1200-1800 words)",
        "item_counts": {
            "min_risks": 5, "risk_range": "5-7",
            "min_objectives": 5, "obj_range": "5-7",
            "min_metrics": 6, "metric_range": "6-8",
            "min_improvements": 3, "table_note": "",
        },
    },
    {
        "name":              "mid",
        "min_ram_gb":        0,
        "min_vram_gb":       6,
        "ollama_timeout":    240,
        "model_swap_delay":  4,
        "num_gpu":           1,
        "num_predict":       2000,
        "length_profile":    "comprehensive (~1200-1800 words)",
        "item_counts": {
            "min_risks": 5, "risk_range": "5-7",
            "min_objectives": 5, "obj_range": "5-7",
            "min_metrics": 6, "metric_range": "6-8",
            "min_improvements": 3, "table_note": "",
        },
    },
    {
        "name":              "cpu_rich",
        "min_ram_gb":        16,
        "min_vram_gb":       0,
        "ollama_timeout":    600,
        "model_swap_delay":  12,
        "num_gpu":           1,
        "num_predict":       1200,
        "length_profile":    "concise but complete (~500-800 words)",
        "item_counts": {
            "min_risks": 3, "risk_range": "3-4",
            "min_objectives": 4, "obj_range": "4-5",
            "min_metrics": 4, "metric_range": "4-6",
            "min_improvements": 3, "table_note": " Keep tables to 3-5 rows.",
        },
    },
    {
        "name":              "low",
        "min_ram_gb":        8,
        "min_vram_gb":       0,
        "ollama_timeout":    900,
        "model_swap_delay":  16,
        "num_gpu":           1,
        "num_predict":       1200,
        "length_profile":    "concise but complete (~500-800 words)",
        "item_counts": {
            "min_risks": 3, "risk_range": "3-4",
            "min_objectives": 4, "obj_range": "4-5",
            "min_metrics": 4, "metric_range": "4-6",
            "min_improvements": 3, "table_note": " Keep tables to 3-5 rows.",
        },
    },
    {
        "name":              "minimal",
        "min_ram_gb":        0,
        "min_vram_gb":       0,
        "ollama_timeout":    900,
        "model_swap_delay":  20,
        "num_gpu":           0,
        "num_predict":       1000,
        "length_profile":    "concise (~400-600 words)",
        "item_counts": {
            "min_risks": 3, "risk_range": "3-4",
            "min_objectives": 4, "obj_range": "4-5",
            "min_metrics": 4, "metric_range": "4-6",
            "min_improvements": 3, "table_note": " Keep tables to 3-5 rows.",
        },
    },
]


def load_models_catalog(path=None):
    """Load the bundled (or an override) models catalog JSON."""
    p = Path(path) if path else _CATALOG_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _build_tiers():
    """Merge _TIER_TUNING (Python, hardware behavior) with models_catalog.json
    (model identity) into the full tier dicts the rest of this module expects."""
    catalog = load_models_catalog()
    tiers = []
    for tuning in _TIER_TUNING:
        entry = catalog["tiers"][tuning["name"]]
        merged = dict(tuning)
        merged.update({
            "gen_model": entry["gen_model"],
            "reviewer_model": entry["reviewer_model"],
            "label": entry["label"],
            "why": entry["why"],
            "speed": entry["speed"],
        })
        tiers.append(merged)
    return tiers


def _build_legacy_factory_models():
    """Factory model tags that apply_to_config() is allowed to overwrite on
    re-detection: current tier models plus every models_catalog.json legacy_tags
    entry (older factory defaults, appended over time, never removed) — so an
    install that picked an old default migrates cleanly. A tag a user typed by
    hand is NOT in this set and is left untouched."""
    catalog = load_models_catalog()
    tags = set(catalog.get("legacy_tags", []))
    for entry in catalog["tiers"].values():
        tags.add(entry["gen_model"])
        tags.add(entry["reviewer_model"])
    return tags


def refresh_catalog_best_effort():
    """Opt-in, manual-only (CLI --refresh-catalog), never called from install's
    default path. Best-effort GET to a public Ollama model index; on ANY failure
    (offline, timeout, malformed response, unexpected schema) this is a silent
    no-op — never raises, never touches the bundled models_catalog.json. On
    success, writes an informational cache file only; does not alter TIERS
    or LEGACY_FACTORY_MODELS for the current process."""
    try:
        resp = requests.get("https://ollamadb.dev/api/v1/models", timeout=5)
        if resp.status_code != 200:
            return
        data = resp.json()
        if not isinstance(data, dict) or "models" not in data:
            return
        _ONLINE_CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"  [OK] Online model index cached to {_ONLINE_CACHE_PATH.name} "
              "(informational only — config.yaml is unaffected).")
    except Exception:
        pass  # advisory only — never block or fail install on this


TIERS = _build_tiers()
LEGACY_FACTORY_MODELS = _build_legacy_factory_models()


# ---------------------------------------------------------------------------
# VRAM detection - three-stage fallback (NVIDIA -> registry -> WMI)
# ---------------------------------------------------------------------------
def _vram_from_nvidia_smi():
    """Stage 1: nvidia-smi (NVIDIA cards only). Returns GB float or 0.
    Single-adapter scalar for backward compat; list variant below."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            timeout=5, stderr=subprocess.DEVNULL,
        )
        return round(int(out.decode().strip().split()[0]) / 1024, 1)
    except Exception:
        return 0


def _vram_list_from_nvidia_smi():
    """Stage 1 (list): returns list of GB floats for every NVIDIA adapter."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            timeout=5, stderr=subprocess.DEVNULL,
        )
        result = []
        for line in out.decode().splitlines():
            line = line.strip()
            if line:
                try:
                    result.append(round(int(line.split()[0]) / 1024, 1))
                except ValueError:
                    pass
        return result
    except Exception:
        return []


def _vram_from_registry():
    """Stage 2: Windows registry HardwareInformation.qwMemorySize (64-bit,
    any vendor). Returns GB float or 0 (max across all adapters)."""
    vals = _vram_list_from_registry()
    return max(vals) if vals else 0


def _vram_list_from_registry():
    """Stage 2 (list): returns list of GB floats for every GPU adapter found
    in HKLM\\...\\{4d36e968} (64-bit qwMemorySize, any vendor)."""
    if platform.system() != "Windows":
        return []
    try:
        import winreg
        base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        result = []
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                if not sub.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, sub) as k:
                        val, _ = winreg.QueryValueEx(k, "HardwareInformation.qwMemorySize")
                        if isinstance(val, (bytes, bytearray)):
                            val = int.from_bytes(val, "little")
                        gb = round(int(val) / 1_073_741_824, 1)
                        if gb > 0:
                            result.append(gb)
                except OSError:
                    continue
        return result
    except Exception:
        return []


def _vram_from_wmi():
    """Stage 3: WMI AdapterRAM (32-bit, caps near 4 GB - last resort).
    Returns GB float or 0 (max across all adapters)."""
    vals = _vram_list_from_wmi()
    return max(vals) if vals else 0


def _vram_list_from_wmi():
    """Stage 3 (list): returns list of GB floats for every video controller
    via WMI AdapterRAM (32-bit field, caps near 4 GB - last resort)."""
    if platform.system() != "Windows":
        return []
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "Select-Object -ExpandProperty AdapterRAM"],
            timeout=10, stderr=subprocess.DEVNULL,
        )
        result = []
        for line in out.decode().splitlines():
            line = line.strip()
            if line.isdigit():
                gb = round(int(line) / 1_073_741_824, 1)
                if gb > 0:
                    result.append(gb)
        return result
    except Exception:
        return []


def detect_vram_list():
    """Return a list of per-adapter VRAM GB values via three-stage fallback.
    If no adapters are found returns an empty list."""
    for stage_list in (_vram_list_from_nvidia_smi, _vram_list_from_registry, _vram_list_from_wmi):
        adapters = stage_list()
        if adapters:
            return adapters
    return []


def detect_vram_gb():
    """Best-available VRAM in GB via three-stage fallback (returns max)."""
    for stage in (_vram_from_nvidia_smi, _vram_from_registry, _vram_from_wmi):
        vram = stage()
        if vram:
            return vram
    return 0


def detect_hardware():
    """Return dict: ram_gb, vram_gb, cpu, os."""
    ram_gb = 0
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / 1_073_741_824, 1)
    except Exception:
        pass

    vram_gb = detect_vram_gb()
    cpu = platform.processor() or platform.machine() or "Unknown CPU"
    os_name = platform.system()

    return {"ram_gb": ram_gb, "vram_gb": vram_gb, "cpu": cpu, "os": os_name}


def select_tier(hw: dict) -> dict:
    """Pick best matching tier - VRAM-fit first, then RAM. A tier qualifies if
    EITHER its VRAM threshold is met (GPU tiers) OR its RAM threshold is met
    (CPU tiers); the two are no longer AND-coupled, so a 32 GB / 0 VRAM box
    lands in cpu_rich instead of falling through to low."""
    ram  = hw["ram_gb"]
    vram = hw["vram_gb"]
    for tier in TIERS:
        gpu_ok = tier["min_vram_gb"] > 0 and vram >= tier["min_vram_gb"]
        cpu_ok = tier["min_vram_gb"] == 0 and ram >= tier["min_ram_gb"]
        if gpu_ok or cpu_ok:
            t = dict(tier)
            if vram < 0.5:           # no usable GPU - force CPU-only
                t["num_gpu"] = 0
            return t
    return dict(TIERS[-1])  # fallback: minimal


def apply_to_config(hw: dict, tier: dict) -> None:
    """Write hardware-calibrated defaults into config.yaml."""
    if not CONFIG_PATH.exists():
        print(f"  ERROR: config.yaml not found at {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    cfg.setdefault("llm", {})
    cfg.setdefault("critic", {})
    cfg.setdefault("timeouts", {})

    # Only overwrite model tags that are still a (current or legacy) factory
    # default - never clobber a tag the user typed by hand.
    if cfg["llm"].get("model", "") in LEGACY_FACTORY_MODELS or not cfg["llm"].get("model"):
        cfg["llm"]["model"] = tier["gen_model"]
    if cfg["critic"].get("model", "") in LEGACY_FACTORY_MODELS or not cfg["critic"].get("model"):
        cfg["critic"]["model"] = tier["reviewer_model"]

    cfg["llm"]["num_gpu"]      = tier["num_gpu"]
    cfg["llm"]["num_predict"]  = tier["num_predict"]

    # pipeline.target_words drives the length directive injected into prompts
    cfg.setdefault("pipeline", {})
    cfg["pipeline"]["target_words"] = tier["length_profile"]

    # generation.item_counts drives per-clause count directives in skill templates
    cfg.setdefault("generation", {})
    cfg["generation"]["item_counts"] = tier["item_counts"]

    # Always write timeouts - these should reflect current hardware
    cfg["timeouts"]["ollama_generate"]  = tier["ollama_timeout"]
    cfg["timeouts"]["model_swap_delay"] = tier["model_swap_delay"]
    cfg["timeouts"]["hardware_tier"]    = tier["name"]
    cfg["timeouts"]["detected_ram_gb"]  = hw["ram_gb"]
    cfg["timeouts"]["detected_vram_gb"] = hw["vram_gb"]

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=True)


def print_models():
    """Emit the detected tier's generator + reviewer tag, one per line.
    install.bat consumes this to pull exactly the models this machine will use."""
    tier = select_tier(detect_hardware())
    print(tier["gen_model"])
    print(tier["reviewer_model"])


def detect_main():
    """Read-only diagnostic: print full hardware metrics + tier without writing config."""
    print()
    print("  [DETECT] Hardware diagnostics (read-only - config.yaml is NOT modified)")
    print()
    hw = detect_hardware()
    print(f"  CPU  : {hw['cpu']}")
    print(f"  RAM  : {hw['ram_gb']} GB")
    print(f"  OS   : {hw['os']}")
    print()

    # Per-adapter VRAM list
    adapters = detect_vram_list()
    if adapters:
        print(f"  GPU adapters found: {len(adapters)}")
        for i, gb in enumerate(adapters):
            print(f"    [{i}] {gb} GB VRAM")
        print(f"  VRAM (max)    : {max(adapters)} GB")
    else:
        print("  GPU adapters  : none detected (CPU-only mode)")

    tier = select_tier(hw)
    print()
    print(f"  Chosen tier   : {tier['name']}  ({tier['label']})")
    print(f"  Why           : {tier['why']}")
    print(f"  Expected speed: {tier['speed']}")
    print(f"  Gen model     : {tier['gen_model']}")
    print(f"  Reviewer      : {tier['reviewer_model']}")
    print(f"  num_predict   : {tier['num_predict']}")
    print(f"  length profile: {tier['length_profile']}")
    print(f"  Ollama timeout: {tier['ollama_timeout']}s")
    print(f"  Swap delay    : {tier['model_swap_delay']}s")
    print()
    print("  (Use setup_config.py without --detect to apply these settings to config.yaml)")


def main():
    print()
    print("  Detecting hardware...")
    hw = detect_hardware()
    print(f"  CPU  : {hw['cpu']}")
    print(f"  RAM  : {hw['ram_gb']} GB")
    print(f"  VRAM : {hw['vram_gb']} GB {'(detected)' if hw['vram_gb'] else '(none / CPU-only)'}")
    print(f"  OS   : {hw['os']}")

    tier = select_tier(hw)
    print()
    print(f"  Hardware tier : {tier['label']}")
    print(f"  Why           : {tier['why']}")
    print(f"  Gen model     : {tier['gen_model']}")
    print(f"  Reviewer      : {tier['reviewer_model']}")
    print(f"  Expected speed: {tier['speed']}")
    print(f"  Ollama timeout: {tier['ollama_timeout']}s")
    print(f"  Swap delay    : {tier['model_swap_delay']}s")

    apply_to_config(hw, tier)
    print()
    print("  [OK]  config.yaml updated with hardware-calibrated settings")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VaultISO27 hardware detection / config.")
    parser.add_argument(
        "--print-models", action="store_true",
        help="Print the detected tier's gen + reviewer model tags (one per line) and exit.",
    )
    parser.add_argument(
        "--detect", action="store_true",
        help="Print full hardware diagnostics (RAM, per-GPU VRAM list, tier) without writing config.yaml.",
    )
    parser.add_argument(
        "--refresh-catalog", action="store_true",
        help="Best-effort check for newer model tags against a public index. Never touches "
             "models_catalog.json or config.yaml; writes an informational cache file only.",
    )
    args = parser.parse_args()
    if args.print_models:
        print_models()
    elif args.detect:
        detect_main()
    elif args.refresh_catalog:
        refresh_catalog_best_effort()
    else:
        main()
