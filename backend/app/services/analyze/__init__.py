"""Orchestrate deterministic ingest and the evidence-gated analysis stages."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ...config import Settings
from ...schemas.findings import Finding
from ...schemas.repo_map import RepoMap
from ...schemas.scores import Scores
from ..ingest import build_repo_map, clone_service, gitlog, metrics
from ..ingest.filter import filter_files
from ..knowledge import get_ladder, get_taxonomy
from .ranker import rank_files
from .scanner import scan_file
from .scorer import score
from .validator import validate


@dataclass(frozen=True)
class AnalysisArtifacts:
    """Typed outputs produced before the persistence boundary."""

    repo_map: RepoMap
    findings: list[Finding]
    dropped_findings: list[Finding]
    scores: Scores
    repository_metrics: dict[str, object]


def _repository_metrics(root: Path, kept_files: list[str]) -> dict[str, object]:
    repository_metrics: dict[str, object] = gitlog.commit_stats(root)
    flags = [flag for rel_path in kept_files for flag in metrics.smell_flags(root, rel_path)]
    for flag_type in ("empty_catch", "swallowed_exception", "hardcoded_secret"):
        repository_metrics[f"{flag_type}_count"] = sum(
            flag["type"] == flag_type for flag in flags
        )
    return repository_metrics


def analyze_repository(
    settings: Settings,
    user: str,
    repo_full_name: str,
    token: str,
    *,
    is_fork: bool = False,
    author_email: str | None = None,
    progress: Callable[[str, int], None] | None = None,
) -> AnalysisArtifacts:
    """Run INGEST -> rank -> scan -> validate -> score for one repository."""
    notify = progress or (lambda _stage, _percent: None)
    notify("ingesting", 5)
    repo_map = build_repo_map(
        settings,
        user,
        repo_full_name,
        token,
        is_fork=is_fork,
        author_email=author_email,
    )
    root = clone_service.cache_path(settings, user, repo_full_name)
    kept_files, _ = filter_files(root, settings.target_language, is_fork)

    candidates: list[Finding] = []
    ranked_files = rank_files(repo_map, settings.scan_file_limit)
    notify("scanning", 35)
    for index, rel_path in enumerate(ranked_files, 1):
        candidates.extend(scan_file(settings, root, rel_path))
        notify("scanning", 35 + round(40 * index / len(ranked_files)))
    findings, dropped_findings = validate(root, candidates)

    notify("scoring", 80)
    repository_metrics = _repository_metrics(root, kept_files)
    scores = score(
        repo_map,
        findings,
        get_ladder(settings),
        get_taxonomy(settings),
        repository_metrics,
    )
    notify("persisting", 95)
    return AnalysisArtifacts(
        repo_map=repo_map,
        findings=findings,
        dropped_findings=dropped_findings,
        scores=scores,
        repository_metrics=repository_metrics,
    )


__all__ = ["AnalysisArtifacts", "analyze_repository"]
