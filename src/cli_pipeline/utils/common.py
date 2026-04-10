#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared utilities extracted from pipeline stages.

Consolidates duplicated code from infer.py, infer_api.py, retrieve.py,
and single_case/prompt.py into a single module.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROMPT_SEPARATOR = "=" * 80


# ---------------------------------------------------------------------------
# Prompt parsing (was duplicated in infer.py and infer_api.py)
# ---------------------------------------------------------------------------

def parse_prompt_block(block_text: str) -> Tuple[Optional[str], Optional[str], str, Optional[str]]:
    """Parse a single prompt block into (system_prompt, user_input, header, error).

    Returns a 4-tuple:
      - system_prompt: text between [Start of Prompt] and [End of Prompt], or None
      - user_input:    text between [Start of Input] and [End of Output], or None
      - header:        e.g. "Prompt 1"
      - error:         error message if parsing failed, else None
    """
    header_match = re.search(r"===\s*(Prompt\s*\d+).*?===", block_text)
    header = header_match.group(1).strip() if header_match else "Unknown Prompt"

    system_match = re.search(
        r"\[Start of Prompt\](.*?)\[End of Prompt\]", block_text, re.DOTALL
    )
    if not system_match:
        return None, None, header, "System prompt markers not found."
    system_prompt = system_match.group(1).strip()

    user_match = re.search(
        r"\[Start of Input\](.*?)\[End of Output\]", block_text, re.DOTALL
    )
    if not user_match:
        return None, None, header, "User input markers not found."
    user_input = user_match.group(0).strip()

    return system_prompt, user_input, header, None


# ---------------------------------------------------------------------------
# Similarity JSON loading (was duplicated in retrieve.py and single_case/prompt.py)
# ---------------------------------------------------------------------------

def load_similarity_json(path: str) -> Dict[str, List[str]]:
    """Load and normalize a similarity JSON file.

    Handles multiple formats:
      - ``{item: [{"Drug": "..."}, ...]}``  or  ``{item: ["x", ...]}``
      - ``{gene: {"direct_neighbors": [...], ...}}``  (uses first recognized list field)
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    out: Dict[str, List[str]] = {}
    for key, vals in raw.items():
        if not vals:
            out[key] = []
            continue

        # dict value  – e.g. gene similarity graph results
        if isinstance(vals, dict):
            for field in (
                "direct_neighbors",
                "neighbors",
                "close_genes",
                "similar_genes",
                "top_genes",
                "two_hop_neighbors",
            ):
                candidates = vals.get(field)
                if isinstance(candidates, list):
                    out[key] = [str(v) for v in candidates]
                    break
            else:
                out[key] = [str(v) for v in vals.values()]
            continue

        # list value
        if isinstance(vals, list):
            if not vals:
                out[key] = []
            elif isinstance(vals[0], dict):
                if "Drug" in vals[0]:
                    out[key] = [v.get("Drug") for v in vals if v.get("Drug")]
                elif "Gene" in vals[0]:
                    out[key] = [v.get("Gene") for v in vals if v.get("Gene")]
                else:
                    out[key] = [str(v) for v in vals]
            else:
                out[key] = [str(v) for v in vals]
            continue

        # scalar fallback
        out[key] = [str(vals)]

    return out


# ---------------------------------------------------------------------------
# API helpers (was duplicated in infer_api.py and single_case/prompt.py)
# ---------------------------------------------------------------------------

def resolve_api_key(cli_key: Optional[str] = None, fallback: str = "") -> str:
    """Resolve API key from CLI arg > env vars > fallback."""
    if cli_key:
        return cli_key
    env_key = os.getenv("LLM_DRUG_API_KEY") or os.getenv("API_KEY")
    if env_key:
        return env_key
    return fallback


def post_json(url: str, payload: dict, api_key: str, timeout: int) -> dict:
    """Send a JSON POST request with optional Bearer auth. Returns parsed JSON."""
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as e:
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            detail = str(e)
        raise RuntimeError(f"API HTTPError: {e.code} {detail}") from e
    except URLError as e:
        raise RuntimeError(f"API URLError: {e.reason}") from e


# ---------------------------------------------------------------------------
# Generic I/O helpers
# ---------------------------------------------------------------------------

def load_json(path: str) -> dict:
    """Load a JSON file and return its contents."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_csv_pairs(path: str) -> List[Tuple[str, str, int, str]]:
    """Load a CSV with columns pert, gene, label, split.

    Returns list of (pert, gene, label, split) tuples.
    """
    pairs: List[Tuple[str, str, int, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        idx_pert = header.index("pert")
        idx_gene = header.index("gene")
        idx_label = header.index("label")
        idx_split = header.index("split")
        for line in f:
            if not line.strip():
                continue
            cols = line.rstrip("\n").split(",")
            if len(cols) <= max(idx_pert, idx_gene, idx_label, idx_split):
                continue
            pairs.append((cols[idx_pert], cols[idx_gene], int(cols[idx_label]), cols[idx_split]))
    return pairs
