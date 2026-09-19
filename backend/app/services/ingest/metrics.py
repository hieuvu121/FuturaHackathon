"""Syntax-tree metrics. Owner: Track A.

Computes cyclomatic complexity, nesting depth, LOC and the call graph.
Detects test files and maps tests back to the functions they cover.
Flags empty catch blocks, swallowed exceptions, hardcoded secrets.
"""

from pathlib import Path

from ...schemas.repo_map import FunctionNode


def enrich(root: Path, functions: list[FunctionNode]) -> list[FunctionNode]:
    """Fills complexity, nesting_depth, calls and has_test in place."""
    raise NotImplementedError


def smell_flags(root: Path, rel_path: str) -> list[dict]:
    """Empty catches, swallowed exceptions, hardcoded secrets -- with line numbers."""
    raise NotImplementedError
