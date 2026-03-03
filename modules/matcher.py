"""
Technology matching engine.
Three-tier strategy:
  Tier 1 – Exact match         (instant)
  Tier 2 – RapidFuzz fuzzy     (fast, C-backed)
  Tier 3 – Azure AI validation (only for ambiguous cases; minimises API cost)
"""
import json
import os
from typing import Callable, Optional

import polars as pl
from rapidfuzz import fuzz, process

from config import FUZZY_AUTO_ACCEPT, FUZZY_SEND_TO_AI, get_azure_config


# ── Azure AI client ───────────────────────────────────────────────────────────

def get_ai_client():
    """Return AzureOpenAI client if credentials are configured, else None."""
    try:
        from openai import AzureOpenAI
        cfg = get_azure_config()
        if not cfg["endpoint"] or not cfg["api_key"]:
            return None
        return AzureOpenAI(
            azure_endpoint=cfg["endpoint"],
            api_key=cfg["api_key"],
            api_version=cfg["api_version"],
        )
    except Exception:
        return None


# ── Individual match functions ────────────────────────────────────────────────

def _fuzzy_best(query: str, choices: list[str]) -> Optional[tuple[str, int, int]]:
    """Return (best_match, score, index) using token_sort_ratio."""
    results = process.extractOne(query, choices, scorer=fuzz.token_sort_ratio)
    return results  # (match_str, score, index) or None


def _ai_validate(tech1: str, tech2: str, client) -> dict:
    """
    Ask Azure AI whether two technology names refer to the same product.
    Returns: {"match": bool, "confidence": int, "reason": str}
    """
    cfg = get_azure_config()
    prompt = (
        "You are a technology naming expert. Determine if the two entries below "
        "refer to the same software product (ignoring minor version differences).\n\n"
        f"Entry 1: {tech1}\n"
        f"Entry 2: {tech2}\n\n"
        'Reply with JSON only: {"match": true/false, "confidence": 0-100, "reason": "brief explanation"}'
    )
    try:
        response = client.chat.completions.create(
            model=cfg["deployment"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"match": False, "confidence": 0, "reason": f"AI error: {e}"}


# ── Main matching function ────────────────────────────────────────────────────

def match_technologies(
    source_techs: list[str],
    ea_techs: list[str],
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[dict]:
    """
    Match a list of Device42 technology names against EA Tool technology names.

    Args:
        source_techs:      Unique technology names from Device42 (after cleaning).
        ea_techs:          Technology names from the EA Tool.
        progress_callback: Optional fn(current, total) for progress reporting.

    Returns:
        List of dicts with keys:
          device42_tech, ea_tech, score, match_type, matched, [ai_reason]
    """
    client = get_ai_client()
    ea_lower = [t.lower().strip() for t in ea_techs]
    results = []

    for i, tech in enumerate(source_techs):
        if progress_callback:
            progress_callback(i + 1, len(source_techs))

        tech_lower = tech.lower().strip()

        # ── Tier 1: Exact match ──────────────────────────────────────────────
        if tech_lower in ea_lower:
            idx = ea_lower.index(tech_lower)
            results.append({
                "device42_tech": tech,
                "ea_tech": ea_techs[idx],
                "score": 100,
                "match_type": "exact",
                "matched": True,
                "ai_reason": "",
            })
            continue

        # ── Tier 2: Fuzzy match ──────────────────────────────────────────────
        best = _fuzzy_best(tech_lower, ea_lower)

        if best and best[1] >= FUZZY_AUTO_ACCEPT:
            results.append({
                "device42_tech": tech,
                "ea_tech": ea_techs[best[2]],
                "score": best[1],
                "match_type": "fuzzy",
                "matched": True,
                "ai_reason": "",
            })
            continue

        # ── Tier 3: AI validation for ambiguous cases ────────────────────────
        if best and best[1] >= FUZZY_SEND_TO_AI and client:
            ai = _ai_validate(tech, ea_techs[best[2]], client)
            if ai.get("match"):
                results.append({
                    "device42_tech": tech,
                    "ea_tech": ea_techs[best[2]],
                    "score": ai.get("confidence", 70),
                    "match_type": "ai",
                    "matched": True,
                    "ai_reason": ai.get("reason", ""),
                })
                continue

        # ── No match ─────────────────────────────────────────────────────────
        results.append({
            "device42_tech": tech,
            "ea_tech": ea_techs[best[2]] if best else "",
            "score": best[1] if best else 0,
            "match_type": "none",
            "matched": False,
            "ai_reason": "",
        })

    return results


def results_to_dataframe(results: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(results)
