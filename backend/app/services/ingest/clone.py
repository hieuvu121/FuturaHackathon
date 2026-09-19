"""Shallow clone into cache/<user>/<repo>/. Owner: Track A."""

import base64
import shutil
from pathlib import Path

from git import Repo

from ...config import Settings


def _safe_segment(value: str, label: str) -> str:
    if not value or value in {".", ".."} or Path(value).name != value:
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _repo_name(repo_full_name: str) -> str:
    parts = repo_full_name.split("/")
    if len(parts) != 2:
        raise ValueError("Repository name must have the form owner/repository")
    _safe_segment(parts[0], "repository owner")
    return _safe_segment(parts[1], "repository name")


def _cache_path(settings: Settings, user: str, repo: str) -> Path:
    user = _safe_segment(user, "user")
    repo = _safe_segment(repo, "repository")
    cache_root = settings.cache_dir.resolve()
    destination = (cache_root / user / repo).resolve()
    if not destination.is_relative_to(cache_root):
        raise ValueError("Clone destination escapes the cache")
    return destination


def _size_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def clone(settings: Settings, user: str, repo_full_name: str, token: str) -> Path:
    """Shallow-clones with depth and size limits. Re-clones if already present."""
    repo_name = _repo_name(repo_full_name)
    destination = _cache_path(settings, user, repo_name)
    cleanup(settings, user, repo_name)
    destination.parent.mkdir(parents=True, exist_ok=True)

    env: dict[str, str] | None = None
    if token:
        credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credentials}",
        }

    try:
        Repo.clone_from(
            f"https://github.com/{repo_full_name}.git",
            destination,
            depth=settings.clone_depth,
            multi_options=["--single-branch", "--no-tags"],
            env=env,
        )
        max_bytes = settings.max_repo_mb * 1024 * 1024
        if _size_bytes(destination) > max_bytes:
            raise ValueError(f"Repository exceeds the {settings.max_repo_mb} MB clone limit")
    except Exception:
        cleanup(settings, user, repo_name)
        raise

    return destination


def cleanup(settings: Settings, user: str, repo_id: str) -> None:
    destination = _cache_path(settings, user, repo_id)
    if destination.exists():
        shutil.rmtree(destination)
