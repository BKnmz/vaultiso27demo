"""Loads the hand-curated OpenRouter-family -> Ollama-tag allowlist."""
import json
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent / "curated_families.json"


def load_curated_families(path=None) -> list:
    """Return the list of curated family dicts from curated_families.json."""
    p = Path(path) if path else _DEFAULT_PATH
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data["families"]
