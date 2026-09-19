"""Background worker for the persisted repository-analysis pipeline."""

import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models.db import Analysis, Repo, SessionLocal, User
from ..schemas.findings import Finding
from ..schemas.repo_map import RepoMap
from ..schemas.scores import Scores
from .analyze import AnalysisArtifacts, analyze_repository, analyze_repository_incremental
from .ingest import clone_service
from .storage import complete_analysis, fail_analysis, update_analysis_progress

logger = logging.getLogger(__name__)


def run_analysis_task(
    settings: Settings,
    analysis_id: int,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """Run one queued analysis using a database session owned by the worker."""
    db = session_factory()
    analysis: Analysis | None = None
    repo: Repo | None = None
    owner: User | None = None
    try:
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            logger.error("Analysis %s disappeared before its worker started", analysis_id)
            return
        repo = db.get(Repo, analysis.repo_id)
        owner = db.get(User, repo.user_id) if repo is not None else None
        if repo is None or owner is None:
            raise RuntimeError("Analysis repository or owner no longer exists")

        def report(stage: str, percent: int) -> None:
            update_analysis_progress(db, analysis, stage, percent)

        previous = db.scalar(
            select(Analysis)
            .where(
                Analysis.repo_id == repo.id,
                Analysis.id < analysis.id,
                Analysis.stage == "done",
                Analysis.repo_map.is_not(None),
                Analysis.scores.is_not(None),
            )
            .order_by(Analysis.id.desc())
            .limit(1)
        )
        common = {
            "is_fork": repo.is_fork,
            "author_email": owner.email,
            "progress": report,
        }
        if previous is None:
            artifacts = analyze_repository(
                settings,
                owner.github_login,
                repo.full_name,
                owner.github_token or "",
                **common,
            )
        else:
            prior = AnalysisArtifacts(
                repo_map=RepoMap.model_validate(previous.repo_map),
                findings=[Finding.model_validate(item) for item in (previous.findings or [])],
                dropped_findings=[],
                scores=Scores.model_validate(previous.scores),
                repository_metrics={},
            )
            artifacts = analyze_repository_incremental(
                settings,
                owner.github_login,
                repo.full_name,
                owner.github_token or "",
                prior,
                **common,
            )
        repo.clone_path = str(
            clone_service.cache_path(settings, owner.github_login, repo.full_name)
        )
        complete_analysis(db, analysis, repo, artifacts)
    except Exception as exc:
        db.rollback()
        if analysis is not None:
            fail_analysis(db, analysis, exc)
        if repo is not None and owner is not None:
            try:
                clone_service.cleanup_repo(settings, owner.github_login, repo.full_name)
            except OSError:
                logger.exception("Could not clean failed clone for %s", repo.full_name)
        logger.exception("Repository analysis %s failed", analysis_id)
    finally:
        db.close()
