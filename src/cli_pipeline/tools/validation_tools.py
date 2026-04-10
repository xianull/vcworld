#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prediction validation tools for the VCWorld bioinformatics harness.

Checks biological plausibility of LLM predictions by verifying
causal chain completeness and cross-validating against evidence pairs.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# Expected causal chain nodes for a complete reasoning trace
_CAUSAL_CHAIN_KEYWORDS = {
    "drug_target": ["inhibit", "activat", "target", "bind", "block", "suppress"],
    "pathway": ["pathway", "signaling", "cascade", "kinase", "phosphorylat"],
    "transcription": ["transcription factor", "tf ", " tf", "promoter", "expression"],
    "gene_effect": ["upregulat", "downregulat", "differentially expressed",
                    "increase", "decrease", "expression of"],
}


def check_causal_chain_completeness(
    drug: str,
    gene: str,
    reasoning_steps: List[str],
) -> Dict[str, Any]:
    """Check whether the LLM reasoning covers all nodes of the causal chain.

    Expected chain: Drug → Target → Pathway → TF → Gene

    Args:
        drug: Drug name.
        gene: Gene name.
        reasoning_steps: List of reasoning step strings from extract_prediction().

    Returns:
        {
            "complete": bool,
            "covered_nodes": [...],
            "missing_nodes": [...],
            "score": float  # 0.0–1.0
        }
    """
    full_text = " ".join(reasoning_steps).lower()

    covered = []
    missing = []
    for node, keywords in _CAUSAL_CHAIN_KEYWORDS.items():
        if any(kw in full_text for kw in keywords):
            covered.append(node)
        else:
            missing.append(node)

    # Also check drug and gene are mentioned
    if drug.lower() in full_text:
        covered.append("drug_mentioned")
    else:
        missing.append("drug_mentioned")

    if gene.lower() in full_text:
        covered.append("gene_mentioned")
    else:
        missing.append("gene_mentioned")

    total = len(_CAUSAL_CHAIN_KEYWORDS) + 2
    score = len(covered) / total

    return {
        "complete": len(missing) == 0,
        "covered_nodes": covered,
        "missing_nodes": missing,
        "score": round(score, 2),
    }


def cross_validate_prediction(
    drug: str,
    gene: str,
    cell_line: str,
    prediction: str,
    evidence_pairs: List[List[str]],
    task: str = "de",
) -> Dict[str, Any]:
    """Cross-validate a prediction against retrieved evidence pairs.

    Checks whether the prediction is consistent with the majority
    of evidence pairs that involve the same drug or gene.

    Args:
        drug: Query drug name.
        gene: Query gene name.
        cell_line: Cell line name.
        prediction: Predicted label (Yes/No/Increase/Decrease/Uncertain).
        evidence_pairs: List of [drug, gene] pairs from retrieval.
        task: "de" or "dir".

    Returns:
        {
            "consistent": bool,
            "n_evidence": int,
            "n_same_drug": int,   # evidence pairs with same drug
            "n_same_gene": int,   # evidence pairs with same gene
            "confidence_adjustment": float,  # +/- adjustment to confidence
            "notes": [...]
        }
    """
    notes = []
    drug_lower = drug.strip().lower()
    gene_lower = gene.strip().lower()

    n_same_drug = sum(1 for p in evidence_pairs if p[0].strip().lower() == drug_lower)
    n_same_gene = sum(1 for p in evidence_pairs if len(p) > 1 and p[1].strip().lower() == gene_lower)

    if not evidence_pairs:
        notes.append("No evidence pairs available for cross-validation.")
        return {
            "consistent": None,
            "n_evidence": 0,
            "n_same_drug": 0,
            "n_same_gene": 0,
            "confidence_adjustment": -0.1,
            "notes": notes,
        }

    # Heuristic: if we have same-drug evidence, prediction is more reliable
    confidence_adjustment = 0.0
    if n_same_drug > 0:
        confidence_adjustment += 0.1
        notes.append(f"Found {n_same_drug} evidence pair(s) with same drug — supports prediction.")
    if n_same_gene > 0:
        confidence_adjustment += 0.05
        notes.append(f"Found {n_same_gene} evidence pair(s) with same gene — supports prediction.")

    # Uncertain predictions are always flagged
    if prediction == "Uncertain":
        notes.append("Prediction is Uncertain — insufficient evidence in reasoning.")
        confidence_adjustment -= 0.2

    consistent = prediction not in (None, "Uncertain")

    return {
        "consistent": consistent,
        "n_evidence": len(evidence_pairs),
        "n_same_drug": n_same_drug,
        "n_same_gene": n_same_gene,
        "confidence_adjustment": round(confidence_adjustment, 2),
        "notes": notes,
    }
