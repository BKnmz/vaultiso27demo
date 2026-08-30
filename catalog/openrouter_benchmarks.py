"""Fetches OpenRouter benchmark scores and ranks curated-family candidates
within a hardware tier's fit. Never raises past the caller in refresh_model_catalog.py
without an explicit try/except there - see the silent-fallback rule in the spec.

Endpoint verified 2026-08-30 against OpenRouter's own docs
(https://openrouter.ai/docs/api/api-reference/benchmarks/list-benchmarks):
GET https://openrouter.ai/api/v1/benchmarks - auth is REQUIRED (a bearer API key),
unlike the original assumption in the design spec that it might be public."""
import os
import requests

_ENDPOINT = "https://openrouter.ai/api/v1/benchmarks"
_TIMEOUT_S = 10


def fetch_benchmarks(session=None) -> list:
    """GET the OpenRouter benchmark list. Raises RuntimeError if no API key is
    configured (OPENROUTER_API_KEY env var) or on a non-200 response, or the
    underlying requests exception (e.g. Timeout) on network failure - callers
    are responsible for catching and falling back to the cached/static catalog."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set - the benchmarks endpoint requires "
            "authentication. Skipping live fetch, falling back to cached catalog."
        )
    getter = (session or requests).get
    resp = getter(_ENDPOINT, params={"task_type": "intelligence"},
                   headers={"Authorization": f"Bearer {api_key}"}, timeout=_TIMEOUT_S)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter benchmark fetch failed: HTTP {resp.status_code}")
    return resp.json()["data"]


def _matches_family(row: dict, family: dict) -> bool:
    haystack = f"{row.get('model_permaslug', '')} {row.get('display_name', '')}".lower()
    return any(needle.lower() in haystack for needle in family["openrouter_match"])


def rank_candidates(families: list, benchmark_rows: list,
                     tier_min_ram_gb: float, tier_min_vram_gb: float) -> list:
    """Match benchmark rows to curated families, filter variants that fit the
    given tier's RAM/VRAM floor, and return up to 3, sorted by intelligence_index
    descending."""
    candidates = []
    for family in families:
        best_score = None
        for row in benchmark_rows:
            if _matches_family(row, family):
                score = row.get("intelligence_index")
                if score is not None and (best_score is None or score > best_score):
                    best_score = score
        if best_score is None:
            continue
        # A tier is either VRAM-gated (min_vram_gb > 0, e.g. "high"/"mid") or
        # RAM-gated (min_vram_gb == 0, e.g. "cpu_rich"/"low"/"minimal") - never
        # both, mirroring setup_config.py's select_tier() gpu_ok/cpu_ok split.
        # A VRAM-gated tier's min_ram_gb is 0 meaning "not the constraint here",
        # not "0 GB of RAM guaranteed" - a machine with 12GB+ VRAM is assumed to
        # have adequate RAM as a side effect, so RAM is never checked for it.
        is_vram_gated_tier = tier_min_vram_gb > 0
        for variant in family["ollama_variants"]:
            if variant["min_vram_gb"] > 0 and variant["min_vram_gb"] > tier_min_vram_gb:
                continue
            if not is_vram_gated_tier and variant["min_ram_gb"] > tier_min_ram_gb:
                continue
            candidates.append({
                "tag": variant["tag"],
                "family": family["name"],
                "intelligence_index": best_score,
                "size_gb": variant["size_gb"],
            })
    candidates.sort(key=lambda c: c["intelligence_index"], reverse=True)
    return candidates[:3]
