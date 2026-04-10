#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Knowledge query tools for the VCWorld bioinformatics harness.

Queries KEGG and STRING REST APIs for pathway and PPI information.
All functions degrade gracefully when network is unavailable.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import urlopen


# ---------------------------------------------------------------------------
# KEGG helpers
# ---------------------------------------------------------------------------

_KEGG_BASE = "https://rest.kegg.jp"


def _kegg_get(endpoint: str, timeout: int = 10) -> str:
    url = f"{_KEGG_BASE}/{endpoint}"
    try:
        with urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except (URLError, OSError):
        return ""


def query_pathway(drug: str, gene: str, timeout: int = 10) -> Dict[str, Any]:
    """Query KEGG for pathways shared between a drug and a gene.

    Args:
        drug: Drug name (used as KEGG compound query).
        gene: Gene symbol (used as KEGG gene query).
        timeout: HTTP timeout in seconds.

    Returns:
        {
            "drug_pathways": [...],   # pathway IDs/names for drug
            "gene_pathways": [...],   # pathway IDs/names for gene
            "shared_pathways": [...], # intersection
            "source": "kegg" | "unavailable"
        }
    """
    drug_pathways: List[str] = []
    gene_pathways: List[str] = []

    # Search drug pathways via KEGG compound
    drug_raw = _kegg_get(f"find/compound/{drug}", timeout=timeout)
    if drug_raw:
        for line in drug_raw.strip().splitlines()[:3]:
            parts = line.split("\t")
            if len(parts) >= 1:
                cpd_id = parts[0].strip()
                link_raw = _kegg_get(f"link/pathway/{cpd_id}", timeout=timeout)
                for lline in link_raw.strip().splitlines():
                    lparts = lline.split("\t")
                    if len(lparts) >= 2:
                        drug_pathways.append(lparts[1].strip())

    # Search gene pathways via KEGG gene (human = hsa)
    gene_raw = _kegg_get(f"find/genes/hsa:{gene}", timeout=timeout)
    if gene_raw:
        for line in gene_raw.strip().splitlines()[:3]:
            parts = line.split("\t")
            if len(parts) >= 1:
                gene_id = parts[0].strip()
                link_raw = _kegg_get(f"link/pathway/{gene_id}", timeout=timeout)
                for lline in link_raw.strip().splitlines():
                    lparts = lline.split("\t")
                    if len(lparts) >= 2:
                        gene_pathways.append(lparts[1].strip())

    shared = list(set(drug_pathways) & set(gene_pathways))
    source = "kegg" if (drug_pathways or gene_pathways) else "unavailable"

    return {
        "drug_pathways": list(set(drug_pathways)),
        "gene_pathways": list(set(gene_pathways)),
        "shared_pathways": shared,
        "source": source,
    }


# ---------------------------------------------------------------------------
# STRING helpers
# ---------------------------------------------------------------------------

_STRING_BASE = "https://string-db.org/api"


def query_ppi(gene: str, top_k: int = 10, species: int = 9606, timeout: int = 10) -> Dict[str, Any]:
    """Query STRING for protein-protein interactions.

    Args:
        gene: Gene symbol.
        top_k: Number of top interactors to return.
        species: NCBI taxonomy ID (9606 = human).
        timeout: HTTP timeout in seconds.

    Returns:
        {
            "interactors": [...],  # gene symbols of top interactors
            "scores": [...],       # combined STRING scores (0–1000)
            "source": "string" | "unavailable"
        }
    """
    url = (
        f"{_STRING_BASE}/json/interaction_partners"
        f"?identifier={gene}&species={species}&limit={top_k}"
    )
    try:
        with urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        interactors = []
        scores = []
        for item in data:
            partner = item.get("preferredName_B") or item.get("stringId_B", "")
            score = item.get("score", 0)
            if partner and partner != gene:
                interactors.append(partner)
                scores.append(score)
        return {"interactors": interactors[:top_k], "scores": scores[:top_k], "source": "string"}
    except (URLError, OSError, json.JSONDecodeError):
        return {"interactors": [], "scores": [], "source": "unavailable"}


# ---------------------------------------------------------------------------
# Gene / drug description helpers
# ---------------------------------------------------------------------------

def get_gene_function(gene: str, timeout: int = 10) -> str:
    """Fetch a brief gene function summary from KEGG.

    Returns an empty string if unavailable.
    """
    raw = _kegg_get(f"get/hsa:{gene}", timeout=timeout)
    if not raw:
        return ""
    # Extract DEFINITION line
    for line in raw.splitlines():
        if line.startswith("DEFINITION"):
            return line.replace("DEFINITION", "").strip()
    return ""


def get_drug_mechanism(drug: str, timeout: int = 10) -> str:
    """Fetch a brief drug mechanism summary from KEGG.

    Returns an empty string if unavailable.
    """
    # Find compound ID first
    raw = _kegg_get(f"find/compound/{drug}", timeout=timeout)
    if not raw:
        return ""
    first_line = raw.strip().splitlines()[0] if raw.strip() else ""
    parts = first_line.split("\t")
    if not parts:
        return ""
    cpd_id = parts[0].strip()
    detail = _kegg_get(f"get/{cpd_id}", timeout=timeout)
    for line in detail.splitlines():
        if line.startswith("NAME") or line.startswith("REMARK"):
            return line.split(None, 1)[-1].strip()
    return ""
