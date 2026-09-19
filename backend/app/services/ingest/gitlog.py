"""Commit history -> churn. Owner: Track A.

Derives per-file churn, hotspots, commit size and cadence, refactor-vs-append
behaviour, and attaches times_modified / last_modified / created_commit.
"""

from pathlib import Path

from ...schemas.repo_map import FunctionNode


def enrich(root: Path, functions: list[FunctionNode]) -> list[FunctionNode]:
    raise NotImplementedError


def commit_stats(root: Path) -> dict:
    """Cadence, median commit size, refactor ratio. Feeds the scorer."""
    raise NotImplementedError
