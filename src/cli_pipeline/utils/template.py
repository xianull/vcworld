#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe template loading — replaces exec()-based approach.

Uses importlib to load template files as proper Python modules,
eliminating the security risks and debugging difficulties of exec().
"""

from __future__ import annotations

import importlib.util
import sys
import types
from typing import Any, Dict


# Default meta-description variables injected into template modules.
# These are placeholder strings used inside f-string templates; they describe
# *what* each section contains rather than providing actual content.
_TEMPLATE_DEFAULTS: Dict[str, str] = {
    "desc_pert": "description of drug that is to perturb the cell",
    "desc_gene": "description of gene, the impact on which you wish to infer",
    "desc_context": "description of cell line in which the genes are expressed",
    "desc_obs": (
        "set of experimental observations that describe the impact of "
        "small molecule perturbations on related genes, to contextualize your answer"
    ),
}


def load_template_vars(template_file: str) -> Dict[str, Any]:
    """Load a template Python file and return its module-level variables.

    This replaces the previous ``exec()``-based loading with ``importlib``,
    which is safer and produces proper tracebacks on errors.

    The template file is expected to define module-level variables such as
    ``cell_lines``, ``prompt_vcworld_DE``, ``choices_de``, etc.  Default
    ``desc_*`` variables are injected into the module namespace *before*
    execution so that f-strings in the template can reference them.
    """
    # Create a unique module name to avoid collisions
    module_name = f"_vcworld_template_{id(template_file)}"

    spec = importlib.util.spec_from_file_location(module_name, template_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load template: {template_file}")

    module = importlib.util.module_from_spec(spec)

    # Inject default desc_* variables so f-strings in the template resolve
    for k, v in _TEMPLATE_DEFAULTS.items():
        setattr(module, k, v)

    # Temporarily register so relative imports (if any) work
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    # Collect all public variables from the module
    result: Dict[str, Any] = {}
    for attr in dir(module):
        if attr.startswith("_"):
            continue
        result[attr] = getattr(module, attr)

    return result
