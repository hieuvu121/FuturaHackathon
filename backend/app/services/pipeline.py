"""Background worker for the persisted repository-analysis pipeline."""

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from ..config import Settings
from ..models.db import Analysis, Repo, SessionLocal, User
from .analyze import analyze_repository
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

        artifacts = analyze_repository(
            settings,
            owner.github_login,
            repo.full_name,
            owner.github_token or "",
            is_fork=repo.is_fork,
            author_email=owner.email,
            progress=report,
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
