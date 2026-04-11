"""Tests for tools/validation_tools.py"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cli_pipeline.tools.validation_tools import (
    check_causal_chain_completeness,
    cross_validate_prediction,
)


def test_causal_chain_complete():
    steps = [
        "DrugA inhibits the target kinase",
        "The signaling pathway cascade is activated",
        "Transcription factor binds the promoter",
        "Gene expression of GeneX increases",
    ]
    result = check_causal_chain_completeness("DrugA", "GeneX", steps)
    assert result["score"] > 0.5
    assert "drug_target" in result["covered_nodes"]


def test_causal_chain_empty():
    result = check_causal_chain_completeness("DrugA", "GeneX", [])
    assert result["score"] == 0.0
    assert result["complete"] is False


def test_causal_chain_drug_gene_mentioned():
    steps = ["DrugA inhibits pathway", "GeneX is upregulated"]
    result = check_causal_chain_completeness("DrugA", "GeneX", steps)
    assert "drug_mentioned" in result["covered_nodes"]
    assert "gene_mentioned" in result["covered_nodes"]


def test_cross_validate_no_evidence():
    result = cross_validate_prediction("DrugA", "GeneX", "C32", "Yes", [], "de")
    assert result["n_evidence"] == 0
    assert result["confidence_adjustment"] < 0


def test_cross_validate_same_drug():
    pairs = [["DrugA", "GeneY"], ["DrugA", "GeneZ"]]
    result = cross_validate_prediction("DrugA", "GeneX", "C32", "Yes", pairs, "de")
    assert result["n_same_drug"] == 2
    assert result["confidence_adjustment"] > 0


def test_cross_validate_uncertain_penalized():
    pairs = [["DrugA", "GeneX"]]
    result = cross_validate_prediction("DrugA", "GeneX", "C32", "Uncertain", pairs, "dir")
    assert result["confidence_adjustment"] < 0


def test_cross_validate_consistent_prediction():
    pairs = [["DrugB", "GeneX"]]
    result = cross_validate_prediction("DrugA", "GeneX", "C32", "Yes", pairs, "de")
    assert result["consistent"] is True
