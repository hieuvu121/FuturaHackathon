"""Assembles the ingest stages into a validated RepoMap and persists it."""

from pathlib import Path

from ...config import Settings
from ...schemas.repo_map import RepoMap


def build_repo_map(settings: Settings, user: str, repo_full_name: str, token: str) -> RepoMap:
    """clone -> filter -> parse -> metrics -> gitlog -> blame -> RepoMap."""
    raise NotImplementedError("Track A: wire the stages in this order")
