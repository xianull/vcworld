#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data validation tools for the VCWorld bioinformatics harness.

Provides gene/drug name validation and statistical validity checks
that can be called by agents before running inference.
"""

from __future__ import annotations

import difflib
from typing import Any, Dict, List, Optional


def validate_gene_names(
    genes: List[str],
    reference_genes: List[str],
    cutoff: float = 0.8,
) -> Dict[str, Any]:
    """Validate gene names against a reference set.

    Args:
        genes: Gene names to validate.
        reference_genes: Known valid gene names.
        cutoff: Similarity threshold for fuzzy suggestions (0–1).

    Returns:
        {
            "valid": [...],       # exact matches
            "invalid": [...],     # no match found
            "suggestions": {      # fuzzy suggestions for invalid names
                "GENE_X": ["GENE_Y", ...]
            }
        }
    """
    ref_lower = {g.strip().lower(): g for g in reference_genes}
    valid, invalid, suggestions = [], [], {}

    for gene in genes:
        key = gene.strip().lower()
        if key in ref_lower:
            valid.append(gene)
        else:
            invalid.append(gene)
            close = difflib.get_close_matches(key, ref_lower.keys(), n=3, cutoff=cutoff)
            if close:
                suggestions[gene] = [ref_lower[c] for c in close]

    return {"valid": valid, "invalid": invalid, "suggestions": suggestions}


def validate_drug_names(
    drugs: List[str],
    reference_drugs: List[str],
    cutoff: float = 0.8,
) -> Dict[str, Any]:
    """Validate drug names against a reference set.

    Same logic as validate_gene_names but for drugs.
    """
    return validate_gene_names(drugs, reference_drugs, cutoff=cutoff)


def check_statistical_validity(
    de_results: Dict[str, Any],
    fdr_threshold: float = 0.05,
    lfc_threshold: float = 0.25,
) -> Dict[str, Any]:
    """Check whether DE results meet statistical thresholds.

    Args:
        de_results: Dict with keys ``pvals_adj`` (list) and ``logfoldchanges`` (list).
        fdr_threshold: Maximum adjusted p-value for significance.
        lfc_threshold: Minimum absolute log-fold-change.

    Returns:
        {
            "is_valid": bool,
            "n_total": int,
            "n_significant": int,
            "issues": [...]   # list of warning strings
        }
    """
    issues = []
    pvals = de_results.get("pvals_adj", [])
    lfcs = de_results.get("logfoldchanges", [])

    if not pvals:
        issues.append("No adjusted p-values provided.")
    if not lfcs:
        issues.append("No log-fold-changes provided.")

    n_total = len(pvals)
    n_sig = sum(
        1 for p, l in zip(pvals, lfcs)
        if p < fdr_threshold and abs(l) > lfc_threshold
    )

    if n_total > 0 and n_sig == 0:
        issues.append(
            f"No genes pass FDR<{fdr_threshold} and |LFC|>{lfc_threshold} thresholds."
        )

    return {
        "is_valid": len(issues) == 0,
        "n_total": n_total,
        "n_significant": n_sig,
        "issues": issues,
    }
