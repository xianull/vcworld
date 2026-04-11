"""Tests for utils/parsing.py"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cli_pipeline.utils.parsing import extract_prediction, validate_prediction


def test_extract_de_yes():
    text = "1) Drug inhibits target\n2) Pathway activated\n3) TF upregulated\n4) Gene expression increases\n5) Yes. Perturbation of DrugA results in differential expression of GeneX"
    result = extract_prediction(text, "de")
    assert result["prediction"] == "Yes"
    assert result["is_valid"] is True


def test_extract_de_no():
    text = "1) Drug has no effect\n2) Pathway unchanged\n3) TF not affected\n4) Gene unchanged\n5) No. Perturbation of DrugA does not impact GeneX"
    result = extract_prediction(text, "de")
    assert result["prediction"] == "No"
    assert result["is_valid"] is True


def test_extract_dir_increase():
    text = "1) Drug activates pathway\n2) Cascade leads to TF\n3) TF binds promoter\n4) Gene upregulated\n5) Increase. Perturbation of DrugA results in an increase in expression of GeneX"
    result = extract_prediction(text, "dir")
    assert result["prediction"] == "Increase"
    assert result["is_valid"] is True


def test_extract_dir_decrease():
    text = "1) Drug suppresses target\n2) Pathway inhibited\n3) TF blocked\n4) Gene downregulated\n5) Decrease. Perturbation of DrugA results in a decrease in expression of GeneX"
    result = extract_prediction(text, "dir")
    assert result["prediction"] == "Decrease"
    assert result["is_valid"] is True


def test_extract_uncertain():
    text = "1) Unclear mechanism\n2) Multiple pathways\n3) Conflicting evidence\n4) Cannot determine\n5) insufficient evidence to conclude"
    result = extract_prediction(text, "dir")
    assert result["prediction"] == "Uncertain"


def test_extract_no_prediction():
    text = "The drug may or may not affect the gene."
    result = extract_prediction(text, "de")
    assert result["prediction"] is None
    assert result["is_valid"] is False


def test_validate_de_valid():
    assert validate_prediction({"prediction": "Yes", "is_valid": True}, "de") is True
    assert validate_prediction({"prediction": "No", "is_valid": True}, "de") is True


def test_validate_de_invalid():
    assert validate_prediction({"prediction": "Increase", "is_valid": True}, "de") is False
    assert validate_prediction({"prediction": None, "is_valid": False}, "de") is False


def test_validate_dir_valid():
    assert validate_prediction({"prediction": "Increase", "is_valid": True}, "dir") is True
    assert validate_prediction({"prediction": "Decrease", "is_valid": True}, "dir") is True
    assert validate_prediction({"prediction": "Uncertain", "is_valid": True}, "dir") is True


def test_reasoning_steps_extracted():
    text = "1) Step one here\n2) Step two here\n3) Step three here\n4) Step four here\n5) Yes. Perturbation of DrugA results in differential expression of GeneX"
    result = extract_prediction(text, "de")
    assert len(result["reasoning_steps"]) >= 1
