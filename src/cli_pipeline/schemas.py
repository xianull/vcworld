#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Type definitions for pipeline stage inputs and outputs.

Uses TypedDict so each stage has a clear, documented contract.
These types serve as documentation and enable static type checking;
they do not enforce runtime validation (use ``validate_*`` helpers
in utils/parsing.py for that).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


# ---------------------------------------------------------------------------
# prepare stage
# ---------------------------------------------------------------------------

class PrepareOutput(TypedDict):
    """Output produced by the ``prepare`` stage."""
    cell_line: str
    de_csv_path: str
    dir_csv_path: str
    train_perturbations: int
    test_perturbations: int
    total_genes: int


# ---------------------------------------------------------------------------
# retrieve stage
# ---------------------------------------------------------------------------

class RetrievedCase(TypedDict):
    """A single test case with its retrieved evidence pairs."""
    test_case: Dict[str, str]        # {"drug": "...", "gene": "..."}
    retrieved_pairs: List[List[str]]  # [[drug, gene], ...]


class RetrieveOutput(TypedDict):
    """Output produced by the ``retrieve`` stage."""
    cases: List[RetrievedCase]
    total_cases: int
    retrieval_json_path: str


# ---------------------------------------------------------------------------
# prompt stage
# ---------------------------------------------------------------------------

class PromptEntry(TypedDict):
    """A single generated prompt with metadata."""
    index: int
    drug: str
    gene: str
    cell_line: str
    header: str    # e.g. "Prompt 1"
    content: str   # full rendered prompt text


class PromptOutput(TypedDict):
    """Output produced by the ``prompt`` stage."""
    prompts: List[PromptEntry]
    total_prompts: int
    prompts_file_path: str


# ---------------------------------------------------------------------------
# infer stage
# ---------------------------------------------------------------------------

class Prediction(TypedDict, total=False):
    """A single structured prediction from LLM inference."""
    header: str                          # e.g. "Prompt 1"
    raw_response: str                    # full LLM output
    prediction: Optional[str]            # extracted label: Yes/No/Increase/Decrease/Uncertain
    confidence: Optional[float]          # 0.0–1.0
    reasoning_steps: Optional[List[str]] # extracted step-by-step reasoning
    is_valid: bool                       # whether prediction was successfully parsed
    error: Optional[str]                 # error message if parsing/inference failed


class InferOutput(TypedDict):
    """Output produced by the ``infer`` / ``infer-api`` stage."""
    predictions: List[Prediction]
    total_predictions: int
    valid_predictions: int
    output_file_path: str
