#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structured parsing of LLM inference outputs.

Extracts predictions (Yes/No/Increase/Decrease/Uncertain),
reasoning steps, and confidence indicators from raw LLM text.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# DE task prediction patterns
# ---------------------------------------------------------------------------

_DE_YES_PATTERNS = [
    re.compile(r"Yes\.\s*Perturbation of .+ results in differential expression", re.IGNORECASE),
    re.compile(r"\byes\b.*differential expression", re.IGNORECASE),
]

_DE_NO_PATTERNS = [
    re.compile(r"No\.\s*Perturbation of .+ does not impact", re.IGNORECASE),
    re.compile(r"\bno\b.*does not impact", re.IGNORECASE),
]

_DE_UNCERTAIN_PATTERNS = [
    re.compile(r"insufficient evidence", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# DIR task prediction patterns
# ---------------------------------------------------------------------------

_DIR_DECREASE_PATTERNS = [
    re.compile(r"Decrease\.\s*Perturbation of .+ results in a decrease", re.IGNORECASE),
    re.compile(r"\bdecrease\b.*in expression", re.IGNORECASE),
]

_DIR_INCREASE_PATTERNS = [
    re.compile(r"Increase\.\s*Perturbation of .+ results in an increase", re.IGNORECASE),
    re.compile(r"\bincrease\b.*in expression", re.IGNORECASE),
]

_DIR_UNCERTAIN_PATTERNS = [
    re.compile(r"insufficient evidence", re.IGNORECASE),
]


def _extract_reasoning_steps(text: str) -> List[str]:
    """Extract numbered reasoning steps (1) ... 2) ... etc.) from LLM output."""
    # Match patterns like "1)", "1.", "**1)**", "**1.**"
    pattern = re.compile(r"(?:^|\n)\s*\**(\d)\)*\.*\**\s*\**(.+?)(?=\n\s*\**\d[\).]|\Z)", re.DOTALL)
    matches = pattern.findall(text)
    steps = []
    for num, content in matches:
        step_text = content.strip()
        # Remove trailing ** markers
        step_text = re.sub(r"\*+$", "", step_text).strip()
        if step_text:
            steps.append(step_text)
    return steps


def _compute_confidence(text: str, prediction: Optional[str]) -> float:
    """Estimate prediction confidence from textual cues.

    This is a heuristic: looks for hedging language, uncertainty markers,
    and strength of concluding statement.
    """
    if prediction is None or prediction == "Uncertain":
        return 0.0

    score = 0.5  # baseline

    # Boost for strong concluding language
    strong_markers = ["clearly", "strongly", "definitively", "conclusively",
                      "robust evidence", "strong evidence", "well-established"]
    for marker in strong_markers:
        if marker in text.lower():
            score += 0.1

    # Penalize hedging language
    hedge_markers = ["may", "might", "possibly", "uncertain", "unclear",
                     "limited evidence", "insufficient", "speculative",
                     "cannot definitively", "difficult to determine"]
    for marker in hedge_markers:
        if marker in text.lower():
            score -= 0.1

    return max(0.0, min(1.0, score))


def extract_prediction(response_text: str, task: str) -> Dict[str, object]:
    """Extract a structured prediction from LLM output.

    Args:
        response_text: Full LLM-generated response.
        task: ``"de"`` or ``"dir"``.

    Returns:
        A dict with keys:
          - ``prediction``: ``"Yes"``/``"No"``/``"Increase"``/``"Decrease"``/``"Uncertain"`` or ``None``
          - ``confidence``: 0.0–1.0
          - ``reasoning_steps``: list of extracted steps
          - ``is_valid``: whether a valid prediction was found
    """
    text = response_text.strip()
    prediction: Optional[str] = None

    # Search from the end of the text (final prediction is usually last)
    # We reverse-search by checking the last 500 chars first
    tail = text[-500:] if len(text) > 500 else text

    if task == "de":
        for pat in _DE_YES_PATTERNS:
            if pat.search(tail):
                prediction = "Yes"
                break
        if prediction is None:
            for pat in _DE_NO_PATTERNS:
                if pat.search(tail):
                    prediction = "No"
                    break
        if prediction is None:
            for pat in _DE_UNCERTAIN_PATTERNS:
                if pat.search(tail):
                    prediction = "Uncertain"
                    break

    elif task == "dir":
        for pat in _DIR_DECREASE_PATTERNS:
            if pat.search(tail):
                prediction = "Decrease"
                break
        if prediction is None:
            for pat in _DIR_INCREASE_PATTERNS:
                if pat.search(tail):
                    prediction = "Increase"
                    break
        if prediction is None:
            for pat in _DIR_UNCERTAIN_PATTERNS:
                if pat.search(tail):
                    prediction = "Uncertain"
                    break

    steps = _extract_reasoning_steps(text)
    confidence = _compute_confidence(text, prediction)

    return {
        "prediction": prediction,
        "confidence": confidence,
        "reasoning_steps": steps,
        "is_valid": prediction is not None,
    }


def validate_prediction(prediction: Dict[str, object], task: str) -> bool:
    """Check whether an extracted prediction is valid for the given task."""
    pred = prediction.get("prediction")
    if pred is None:
        return False
    if task == "de":
        return pred in ("Yes", "No", "Uncertain")
    if task == "dir":
        return pred in ("Increase", "Decrease", "Uncertain")
    return False
