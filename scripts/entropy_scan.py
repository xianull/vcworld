#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VCWorld Entropy Scanner — Harness Engineering P4 (Continuous Entropy Management)

Scans the codebase for quality drift and assigns grades to each module.
Run periodically on the server (e.g., via cron) to detect degradation early.

Usage:
    python3 scripts/entropy_scan.py --src-dir src/cli_pipeline --report entropy_report.json
    python3 scripts/entropy_scan.py --src-dir src/cli_pipeline --fail-below 0.6

Exit codes:
    0 — all modules pass threshold
    1 — one or more modules below threshold
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

@dataclass
class ModuleGrade:
    path: str
    grade: float          # 0.0 – 1.0
    issues: List[str]
    checks_passed: int
    checks_total: int


def _check_no_exec(source: str) -> Optional[str]:
    """Fail if exec() is used (unsafe template loading)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "SyntaxError: cannot parse file"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "exec":
                return "exec() usage detected — use importlib instead"
    return None


def _check_no_print_in_lib(source: str, path: str) -> Optional[str]:
    """Warn if print() is used in library code (not scripts or cli.py)."""
    if "scripts/" in path or path.endswith("cli.py"):
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                return "print() in library code — use StageLogger instead"
    return None


def _check_has_docstring(source: str) -> Optional[str]:
    """Warn if module has no module-level docstring."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if not (tree.body and isinstance(tree.body[0], ast.Expr) and
            isinstance(tree.body[0].value, ast.Constant)):
        return "Missing module-level docstring"
    return None


def _check_no_bare_except(source: str) -> Optional[str]:
    """Fail if bare except: is used."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            return "Bare except: clause detected — catch specific exceptions"
    return None


def _check_layer_imports(source: str, path: str) -> Optional[str]:
    """Check that utils/ doesn't import from tools/ or stages/."""
    if "utils/" not in path and "/utils/" not in path:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            for alias in getattr(node, "names", []):
                module = module or alias.name
            if "tools" in module or "stages" in module:
                return f"Layer violation: utils imports from {module}"
    return None


CHECKS = [
    _check_no_exec,
    _check_no_bare_except,
    _check_layer_imports,
    _check_has_docstring,
    _check_no_print_in_lib,
]

# Weights: critical checks count more
WEIGHTS = {
    _check_no_exec.__name__: 2.0,
    _check_no_bare_except.__name__: 1.5,
    _check_layer_imports.__name__: 2.0,
    _check_has_docstring.__name__: 0.5,
    _check_no_print_in_lib.__name__: 0.5,
}


def grade_module(path: str) -> ModuleGrade:
    """Run all checks on a single Python file and return a grade."""
    try:
        source = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return ModuleGrade(path=path, grade=0.0, issues=[str(e)],
                           checks_passed=0, checks_total=len(CHECKS))

    issues = []
    total_weight = 0.0
    passed_weight = 0.0

    for check in CHECKS:
        w = WEIGHTS.get(check.__name__, 1.0)
        total_weight += w
        issue = check(source, path) if check.__code__.co_argcount == 2 else check(source)
        if issue:
            issues.append(issue)
        else:
            passed_weight += w

    grade = passed_weight / total_weight if total_weight > 0 else 1.0
    return ModuleGrade(
        path=path,
        grade=round(grade, 2),
        issues=issues,
        checks_passed=sum(1 for c in CHECKS
                          if not (c(source, path) if c.__code__.co_argcount == 2 else c(source))),
        checks_total=len(CHECKS),
    )


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_directory(src_dir: str) -> List[ModuleGrade]:
    """Scan all .py files under src_dir."""
    results = []
    for py_file in sorted(Path(src_dir).rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        results.append(grade_module(str(py_file)))
    return results


def print_report(grades: List[ModuleGrade], threshold: float) -> None:
    """Print a human-readable report."""
    print("\n=== VCWorld Entropy Scan Report ===\n")
    failed = []
    for g in grades:
        status = "PASS" if g.grade >= threshold else "FAIL"
        bar = "#" * int(g.grade * 20) + "." * (20 - int(g.grade * 20))
        rel_path = g.path.replace(os.getcwd() + "/", "")
        print(f"[{status}] {rel_path}")
        print(f"       Grade: {g.grade:.2f} [{bar}]  ({g.checks_passed}/{g.checks_total} checks)")
        for issue in g.issues:
            print(f"       ⚠  {issue}")
        if g.grade < threshold:
            failed.append(g)

    avg = sum(g.grade for g in grades) / len(grades) if grades else 0.0
    print(f"\n{'='*40}")
    print(f"Files scanned : {len(grades)}")
    print(f"Average grade : {avg:.2f}")
    print(f"Below threshold ({threshold:.2f}): {len(failed)}")
    if failed:
        print("\nFailed modules:")
        for g in failed:
            print(f"  - {g.path}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="VCWorld entropy scanner")
    parser.add_argument("--src-dir", default="src/cli_pipeline",
                        help="Directory to scan (default: src/cli_pipeline)")
    parser.add_argument("--report", default=None,
                        help="Write JSON report to this file")
    parser.add_argument("--fail-below", type=float, default=0.6,
                        help="Exit 1 if any module grades below this (default: 0.6)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress human-readable output")
    args = parser.parse_args()

    grades = scan_directory(args.src_dir)

    if not args.quiet:
        print_report(grades, args.fail_below)

    if args.report:
        report = {
            "src_dir": args.src_dir,
            "threshold": args.fail_below,
            "average_grade": round(sum(g.grade for g in grades) / len(grades), 2) if grades else 0.0,
            "modules": [asdict(g) for g in grades],
        }
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"Report written to: {args.report}")

    failed = [g for g in grades if g.grade < args.fail_below]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
