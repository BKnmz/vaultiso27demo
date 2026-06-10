"""
VaultISO27 - Hardware detection and config auto-configuration.
Run once during install (called by install.bat after packages are installed).
Detects RAM, VRAM (NVIDIA + AMD/Intel fallback), CPU; selects hardware tier;
writes calibrated defaults to config.yaml.

Usage:
  python setup_config.py               # normal install flow
  python setup_config.py --print-models # emit gen_model then reviewer_model (one per line)
"""
import platform
import subprocess
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"

# Models previously shipped as factory defaults - treated as overwrite-safe
# so hardware re-detection migrates old installs cleanly.
LEGACY_FACTORY_MODELS = {
    "phi4-mini:3.8b-q4_K_M",
    "qwen2.5:1.5b",
    "qwen2.5:1.5b-q4_K_M",
    "llama3.2:3b-q4_K_M",
    "mistral:7b-q4_K_M",
    # v0.4.1 briefly shipped Gemma 4 as the cpu_rich/low default - too slow
    # when spilled out of VRAM; those installs migrate back on re-detection.
    "gemma4:e2b-it-qat",
    "gemma4:e4b-it-qat",
    "gemma4:12b-it-qat",
}

# ---------------------------------------------------------------------------
# Hardware tiers - speed-first selection.
#
# Principle: a model that FITS in VRAM generates at GPU speed; one that spills
# to CPU runs 5-10x slower. So each tier picks the highest-quality generator
# that actually fits the available VRAM - and when nothing meaningful fits,
# falls back to a model small enough to run tolerably on CPU+RAM. A bigger
# model that spills is never recommended: it costs minutes per document.
#
# All model tags verified against live Ollama registry.
# ---------------------------------------------------------------------------
TIERS = [
    {
        "name":             "high",
        "label":            "High-end (12 GB+ VRAM)",
        "ollama_timeout":   300,
        "model_swap_delay": 4,
        "gen_model":        "gemma4:12b-it-qat",       # 7.2 GB + KV cache - fits 12 GB VRAM
        "reviewer_model":   "qwen2.5:1.5b",
        "num_gpu":          1,
        "why":              "gemma4:12b fits entirely in VRAM - best quality at GPU speed",
        "speed":            "~1-2 min per document",
    },
    {
        "name":             "mid",
        "label":            "Mid-range (6-12 GB VRAM)",
        "ollama_timeout":   480,
        "model_swap_delay": 8,
        "gen_model":        "gemma4:e4b-it-qat",       # 6.1 GB - fits (mostly) in 6-12 GB VRAM
        "reviewer_model":   "qwen2.5:1.5b",
        "num_gpu":          1,
        "why":              "gemma4:e4b fits in VRAM - strong quality at GPU speed",
        "speed":            "~2-4 min per document",
    },
    {
        "name":             "cpu_rich",
        "label":            "CPU-rich (16 GB+ RAM, <6 GB VRAM)",
        "ollama_timeout":   900,
        "model_swap_delay": 15,
        "gen_model":        "phi4-mini:3.8b-q4_K_M",   # ~2.5 GB - small enough to run tolerably on CPU+RAM
        "reviewer_model":   "qwen2.5:1.5b",
        "num_gpu":          1,                          # partial GPU offload; forced 0 if no GPU
        "why":              "no model worth running fits this VRAM - a small fast model on CPU+RAM "
                            "beats a big one spilling out of VRAM at 5-10x slower",
        "speed":            "~8-15 min per document",
    },
    {
        "name":             "low",
        "label":            "Standard (8-16 GB RAM)",
        "ollama_timeout":   600,
        "model_swap_delay": 12,
        "gen_model":        "phi4-mini:3.8b-q4_K_M",   # ~2.5 GB - smallest capable generator
        "reviewer_model":   "qwen2.5:1.5b",
        "num_gpu":          1,
        "why":              "limited RAM - small fast model keeps generation usable",
        "speed":            "~10-20 min per document",
    },
    {
        "name":             "minimal",
        "label":            "Minimal (< 8 GB RAM, CPU-only)",
        "ollama_timeout":   900,
        "model_swap_delay": 20,
        "gen_model":        "qwen2.5:1.5b",            # 0.9 GB - only viable on tiny RAM
        "reviewer_model":   "qwen2.5:1.5b",
        "num_gpu":          0,
        "why":              "last resort - only a 0.9 GB model runs on this little RAM",
        "speed":            "~5-10 min per document (quality limited)",
    },
]


def _detect_vram_gb() -> float:
    """Return GPU VRAM in GB. Tries NVIDIA first, then AMD/Intel via WMI/registry."""
    # 1. NVIDIA via nvidia-smi
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            timeout=5, stderr=subprocess.DEVNULL,
        )
        mb = int(out.decode().strip().split()[0])
        return round(mb / 1024, 1)
    except Exception:
        pass

    # 2. Any GPU on Windows - registry 64-bit VRAM value (works for AMD, Intel, NVIDIA)
    if platform.system() == "Windows":
        try:
            ps = (
                "Get-ItemProperty -Path "
                "'HKLM:\\SYSTEM\\ControlSet001\\Control\\Class\\"
                "{4d36e968-e325-11ce-bfc1-08002be10318}\\0*' "
                "-Name 'HardwareInformation.qwMemorySize' "
                "-ErrorAction SilentlyContinue | "
                "Measure-Object -Property 'HardwareInformation.qwMemorySize' "
                "-Maximum | Select-Object -ExpandProperty Maximum"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps],
                timeout=8, stderr=subprocess.DEVNULL,
            )
            raw = out.decode().strip()
            if raw and raw != "0":
                return round(int(raw) / 1_073_741_824, 1)
        except Exception:
            pass

        # 3. WMI AdapterRAM (32-bit, caps at ~4 GB for large cards - last resort)
        try:
            ps2 = (
                "Get-WmiObject Win32_VideoController | "
                "Where-Object {$_.AdapterRAM -gt 0} | "
                "Measure-Object AdapterRAM -Maximum | "
                "Select-Object -ExpandProperty Maximum"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps2],
                timeout=8, stderr=subprocess.DEVNULL,
            )
            raw = out.decode().strip()
            if raw and raw != "0":
                return round(int(raw) / 1_073_741_824, 1)
        except Exception:
            pass

    return 0.0


def detect_hardware() -> dict:
    """Return dict: ram_gb, vram_gb, cpu, os."""
    ram_gb = 0.0
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / 1_073_741_824, 1)
    except Exception:
        pass

    vram_gb = _detect_vram_gb()
    cpu     = platform.processor() or platform.machine() or "Unknown CPU"
    os_name = platform.system()

    return {"ram_gb": ram_gb, "vram_gb": vram_gb, "cpu": cpu, "os": os_name}


def select_tier(hw: dict) -> dict:
    """
    Pick best matching tier - VRAM-fit first.

    A model only earns a GPU tier if it actually fits the card's VRAM;
    otherwise it spills to CPU and runs 5-10x slower than a smaller model
    would. RAM alone never qualifies a machine for a big model: 32 GB RAM
    with no GPU still generates at CPU speed, so it gets the small fast
    generator (cpu_rich), not a 7 GB model.
    """
    ram  = hw["ram_gb"]
    vram = hw["vram_gb"]

    if vram >= 12:
        tier_name = "high"
    elif vram >= 6:
        tier_name = "mid"
    elif ram >= 16:
        tier_name = "cpu_rich"
    elif ram >= 8:
        tier_name = "low"
    else:
        tier_name = "minimal"

    t = next(t for t in TIERS if t["name"] == tier_name)
    t = dict(t)
    if vram < 0.5:
        t["num_gpu"] = 0
    return t


def apply_to_config(hw: dict, tier: dict) -> None:
    """Write hardware-calibrated defaults into config.yaml."""
    if not CONFIG_PATH.exists():
        print(f"  ERROR: config.yaml not found at {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    cfg.setdefault("llm",     {})
    cfg.setdefault("critic",  {})
    cfg.setdefault("timeouts", {})

    # Overwrite model only if currently a factory/legacy default (not user-custom)
    factory_gen = {t["gen_model"] for t in TIERS} | LEGACY_FACTORY_MODELS
    if cfg["llm"].get("model", "") in factory_gen or not cfg["llm"].get("model"):
        cfg["llm"]["model"] = tier["gen_model"]

    factory_rev = {t["reviewer_model"] for t in TIERS} | LEGACY_FACTORY_MODELS
    if cfg["critic"].get("model", "") in factory_rev or not cfg["critic"].get("model"):
        cfg["critic"]["model"] = tier["reviewer_model"]

    cfg["llm"]["num_gpu"] = tier["num_gpu"]

    cfg["timeouts"]["ollama_generate"]  = tier["ollama_timeout"]
    cfg["timeouts"]["model_swap_delay"] = tier["model_swap_delay"]
    cfg["timeouts"]["hardware_tier"]    = tier["name"]
    cfg["timeouts"]["detected_ram_gb"]  = hw["ram_gb"]
    cfg["timeouts"]["detected_vram_gb"] = hw["vram_gb"]

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=True)


def main() -> None:
    print()
    print("  Detecting hardware...")
    hw = detect_hardware()
    print(f"  CPU  : {hw['cpu']}")
    print(f"  RAM  : {hw['ram_gb']} GB")
    print(f"  VRAM : {hw['vram_gb']} GB {'(GPU detected)' if hw['vram_gb'] else '(none / CPU-only)'}")
    print(f"  OS   : {hw['os']}")

    tier = select_tier(hw)
    print()
    print(f"  Hardware tier  : {tier['label']}")
    print(f"  Gen model      : {tier['gen_model']}")
    print(f"  Why            : {tier['why']}")
    print(f"  Expected speed : {tier['speed']}")
    print(f"  Reviewer       : {tier['reviewer_model']}")
    print(f"  Ollama timeout : {tier['ollama_timeout']}s")
    print(f"  Swap delay     : {tier['model_swap_delay']}s")

    apply_to_config(hw, tier)
    print()
    print("  [OK]  config.yaml updated with hardware-calibrated settings")


if __name__ == "__main__":
    if "--print-models" in sys.argv:
        # Used by install.bat to pull exactly the tier-selected models.
        # Emits: line 1 = gen_model, line 2 = reviewer_model. No other output.
        hw   = detect_hardware()
        tier = select_tier(hw)
        print(tier["gen_model"])
        print(tier["reviewer_model"])
        sys.exit(0)
    main()
