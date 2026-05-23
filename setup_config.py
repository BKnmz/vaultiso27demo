"""
VaultISO27 — Hardware detection and config auto-configuration.
Run once during install (called by install.bat after packages are installed).
Detects RAM, VRAM, CPU; selects appropriate hardware tier; writes defaults
to config.yaml so timeouts/models/num_gpu are calibrated for this machine.
"""
import platform
import subprocess
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"

# ---------------------------------------------------------------------------
# Hardware tiers — ordered best to worst, first match wins
# ---------------------------------------------------------------------------
TIERS = [
    {
        "name":              "high",
        "label":             "High-end (32 GB+ RAM · 8 GB+ VRAM)",
        "min_ram_gb":        32,
        "min_vram_gb":       8,
        "ollama_timeout":    120,
        "model_swap_delay":  2,
        "gen_model":         "mistral:7b-q4_K_M",
        "reviewer_model":    "llama3.2:3b-q4_K_M",
        "num_gpu":           1,
    },
    {
        "name":              "mid",
        "label":             "Mid-range (16–32 GB RAM · 4–8 GB VRAM)",
        "min_ram_gb":        16,
        "min_vram_gb":       4,
        "ollama_timeout":    300,
        "model_swap_delay":  6,
        "gen_model":         "llama3.2:3b-q4_K_M",
        "reviewer_model":    "qwen2.5:1.5b",
        "num_gpu":           1,
    },
    {
        "name":              "low",
        "label":             "Standard (8–20 GB RAM · 0–4 GB VRAM)",
        "min_ram_gb":        8,
        "min_vram_gb":       0,
        "ollama_timeout":    600,
        "model_swap_delay":  12,
        "gen_model":         "phi4-mini:3.8b-q4_K_M",
        "reviewer_model":    "qwen2.5:1.5b",
        "num_gpu":           1,
    },
    {
        "name":              "minimal",
        "label":             "Minimal (< 8 GB RAM · CPU-only)",
        "min_ram_gb":        0,
        "min_vram_gb":       0,
        "ollama_timeout":    900,
        "model_swap_delay":  20,
        "gen_model":         "qwen2.5:1.5b",
        "reviewer_model":    "qwen2.5:1.5b",
        "num_gpu":           0,
    },
]


def detect_hardware():
    """Return dict: ram_gb, vram_gb, cpu, os."""
    ram_gb = 0
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / 1_073_741_824, 1)
    except Exception:
        pass

    vram_gb = 0
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            timeout=5, stderr=subprocess.DEVNULL,
        )
        vram_gb = round(int(out.decode().strip().split()[0]) / 1024, 1)
    except Exception:
        pass

    cpu = platform.processor() or platform.machine() or "Unknown CPU"
    os_name = platform.system()

    return {"ram_gb": ram_gb, "vram_gb": vram_gb, "cpu": cpu, "os": os_name}


def select_tier(hw: dict) -> dict:
    """Pick best matching tier for detected hardware."""
    ram  = hw["ram_gb"]
    vram = hw["vram_gb"]
    for tier in TIERS:
        if ram >= tier["min_ram_gb"] and vram >= tier["min_vram_gb"]:
            t = dict(tier)
            # No GPU: force num_gpu=0 regardless of tier
            if vram < 0.5:
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

    # Only set model/num_gpu if still at factory defaults (don't overwrite user changes)
    factory_gen_models = {t["gen_model"] for t in TIERS}
    if cfg["llm"].get("model", "") in factory_gen_models or not cfg["llm"].get("model"):
        cfg["llm"]["model"] = tier["gen_model"]

    factory_rev_models = {t["reviewer_model"] for t in TIERS}
    if cfg["critic"].get("model", "") in factory_rev_models or not cfg["critic"].get("model"):
        cfg["critic"]["model"] = tier["reviewer_model"]

    cfg["llm"]["num_gpu"] = tier["num_gpu"]

    # Always write timeouts — these should reflect current hardware
    cfg["timeouts"]["ollama_generate"]  = tier["ollama_timeout"]
    cfg["timeouts"]["model_swap_delay"] = tier["model_swap_delay"]
    cfg["timeouts"]["hardware_tier"]    = tier["name"]
    cfg["timeouts"]["detected_ram_gb"]  = hw["ram_gb"]
    cfg["timeouts"]["detected_vram_gb"] = hw["vram_gb"]

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=True)


def main():
    print()
    print("  Detecting hardware...")
    hw = detect_hardware()
    print(f"  CPU  : {hw['cpu']}")
    print(f"  RAM  : {hw['ram_gb']} GB")
    print(f"  VRAM : {hw['vram_gb']} GB {'(NVIDIA)' if hw['vram_gb'] else '(none / CPU-only)'}")
    print(f"  OS   : {hw['os']}")

    tier = select_tier(hw)
    print()
    print(f"  Hardware tier : {tier['label']}")
    print(f"  Gen model     : {tier['gen_model']}")
    print(f"  Reviewer      : {tier['reviewer_model']}")
    print(f"  Ollama timeout: {tier['ollama_timeout']}s")
    print(f"  Swap delay    : {tier['model_swap_delay']}s")

    apply_to_config(hw, tier)
    print()
    print("  [OK]  config.yaml updated with hardware-calibrated settings")


if __name__ == "__main__":
    main()
