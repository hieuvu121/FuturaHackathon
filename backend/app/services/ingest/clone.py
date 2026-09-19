"""Shallow clone into cache/<user>/<repo>/. Owner: Track A."""

from pathlib import Path

from ...config import Settings


def clone(settings: Settings, user: str, repo_full_name: str, token: str) -> Path:
    """Shallow-clones with depth and size limits. Re-clones if already present."""
    raise NotImplementedError


def cleanup(settings: Settings, user: str, repo_id: str) -> None:
    raise NotImplementedError
