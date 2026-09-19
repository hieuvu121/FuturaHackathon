"""Assemble the deterministic ingest stages into a validated ``RepoMap``."""

from datetime import datetime, timezone

from ...config import Settings
from ...schemas.repo_map import FunctionNode, RepoMap
from . import blame as blame_service
from . import clone as clone_service
from . import gitlog, metrics
from .filter import filter_files
from .parser import parse_file


def build_repo_map(
    settings: Settings,
    user: str,
    repo_full_name: str,
    token: str,
    *,
    is_fork: bool = False,
    author_email: str | None = None,
) -> RepoMap:
    """Clone, inspect, and return every eligible function in a repository.

    The cached clone is deliberately retained: later analysis and recall stages
    read source through the pointers in the returned map. Persistence is handled
    by the pipeline rather than this deterministic service.
    """
    root = clone_service.clone(settings, user, repo_full_name, token)
    kept_files, excluded_files = filter_files(root, settings.target_language, is_fork)

    functions: list[FunctionNode] = []
    for rel_path in kept_files:
        functions.extend(parse_file(root, rel_path))

    metrics.enrich(root, functions)
    gitlog.enrich(root, functions)
    if settings.enable_blame and author_email:
        blame_service.enrich(root, functions, author_email)

    return RepoMap(
        repo=repo_full_name,
        language=settings.target_language,
        analyzed_at=datetime.now(timezone.utc),
        total_files=len(kept_files),
        excluded_files=excluded_files,
        functions=functions,
    )


def build_repo_map_incremental(
    settings: Settings,
    user: str,
    repo_full_name: str,
    token: str,
    previous: RepoMap,
    *,
    is_fork: bool = False,
    author_email: str | None = None,
) -> tuple[RepoMap, list[str] | None]:
    """Reuse unchanged parsed functions and parse only files changed on GitHub."""
    synced = clone_service.sync(settings, user, repo_full_name, token)
    kept_files, excluded_files = filter_files(
        synced.root, settings.target_language, is_fork
    )
    kept = set(kept_files)
    changed = set(synced.changed_files or kept_files)
    functions = [
        function
        for function in previous.functions
        if function.file in kept and function.file not in changed
    ]
    for rel_path in kept_files:
        if rel_path in changed:
            functions.extend(parse_file(synced.root, rel_path))

    metrics.enrich(synced.root, functions)
    gitlog.enrich(synced.root, functions)
    if settings.enable_blame and author_email:
        blame_service.enrich(synced.root, functions, author_email)

    return (
        RepoMap(
            repo=repo_full_name,
            language=settings.target_language,
            analyzed_at=datetime.now(timezone.utc),
            total_files=len(kept_files),
            excluded_files=excluded_files,
            functions=functions,
        ),
        synced.changed_files,
    )
