"""Shallow clone into cache/<user>/<repo>/. Owner: Track A."""

import base64
from dataclasses import dataclass
import os
import shutil
import stat
from pathlib import Path

from git import Repo

from ...config import Settings


@dataclass(frozen=True)
class SyncResult:
    root: Path
    previous_commit: str | None
    current_commit: str
    changed_files: list[str] | None

    @property
    def is_incremental(self) -> bool:
        return self.changed_files is not None


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


def cache_path(settings: Settings, user: str, repo_full_name: str) -> Path:
    """Return the validated cache location for an ``owner/repository`` name."""
    return _cache_path(settings, user, _repo_name(repo_full_name))


def _size_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _git_env(token: str) -> dict[str, str] | None:
    if not token:
        return None
    credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credentials}",
    }


def clone(settings: Settings, user: str, repo_full_name: str, token: str) -> Path:
    """Shallow-clones with depth and size limits. Re-clones if already present."""
    repo_name = _repo_name(repo_full_name)
    destination = cache_path(settings, user, repo_full_name)
    cleanup(settings, user, repo_name)
    destination.parent.mkdir(parents=True, exist_ok=True)

    env = _git_env(token)

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


def sync(settings: Settings, user: str, repo_full_name: str, token: str) -> SyncResult:
    """Fetch an existing cached clone, returning the files changed since the last run.

    The first run still performs the full shallow clone. Later runs retain the clone
    and update it to the fetched remote HEAD, which is the basis for partial parsing.
    """
    destination = cache_path(settings, user, repo_full_name)
    try:
        repository = Repo(destination)
        if repository.bare or not repository.remotes:
            raise ValueError("Cached repository is not a usable clone")
    except Exception:
        root = clone(settings, user, repo_full_name, token)
        return SyncResult(
            root=root,
            previous_commit=None,
            current_commit=Repo(root).head.commit.hexsha,
            changed_files=None,
        )

    previous_commit = repository.head.commit.hexsha
    env = _git_env(token) or {}
    try:
        with repository.git.custom_environment(**env):
            repository.remote("origin").fetch(depth=settings.clone_depth, prune=True)
        current_commit = repository.commit("FETCH_HEAD").hexsha
        if current_commit == previous_commit:
            return SyncResult(destination, previous_commit, current_commit, [])
        changed_files = sorted(
            path
            for path in repository.git.diff(
                "--name-only", previous_commit, current_commit
            ).splitlines()
            if path
        )
        repository.git.reset("--hard", current_commit)
        max_bytes = settings.max_repo_mb * 1024 * 1024
        if _size_bytes(destination) > max_bytes:
            raise ValueError(f"Repository exceeds the {settings.max_repo_mb} MB clone limit")
        return SyncResult(destination, previous_commit, current_commit, changed_files)
    except Exception:
        cleanup_repo(settings, user, repo_full_name)
        raise


def _force_remove(function, path, _exc) -> None:
    """Git marks its pack files read-only, and Windows refuses to delete a
    read-only file. Clear the bit and try once more; a second failure is real."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


def cleanup(settings: Settings, user: str, repo_id: str) -> None:
    destination = _cache_path(settings, user, repo_id)
    if destination.exists():
        shutil.rmtree(destination, onexc=_force_remove)


def cleanup_repo(settings: Settings, user: str, repo_full_name: str) -> None:
    """Remove the validated cache location for an ``owner/repository`` name."""
    cleanup(settings, user, _repo_name(repo_full_name))
