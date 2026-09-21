"""Transactional persistence and ownership-checked analysis lookups."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.db import Analysis, QuestionRow, Repo, SkillStatusRow, User
from .analyze import AnalysisArtifacts


def get_owned_repo(db: Session, repo_id: str | int, github_login: str) -> Repo | None:
    """Return a repository only when it belongs to the authenticated user."""
    try:
        numeric_repo_id = int(repo_id)
    except (TypeError, ValueError):
        return None
    return db.scalar(
        select(Repo)
        .join(User, Repo.user_id == User.id)
        .where(Repo.id == numeric_repo_id, User.github_login == github_login)
    )


def latest_analysis(db: Session, repo_id: int) -> Analysis | None:
    return db.scalar(
        select(Analysis)
        .where(Analysis.repo_id == repo_id)
        .order_by(Analysis.id.desc())
        .limit(1)
    )


def start_analysis(db: Session, repo: Repo) -> Analysis:
    """Create a durable queued record before expensive work starts."""
    analysis = Analysis(repo_id=repo.id, stage="queued", progress=0)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def update_analysis_progress(
    db: Session,
    analysis: Analysis,
    stage: str,
    progress: int,
) -> None:
    if not 0 <= progress < 100:
        raise ValueError("In-progress percentage must be between 0 and 99")
    analysis.stage = stage
    analysis.progress = progress
    analysis.error = None
    db.commit()


def _merge_evidence(existing: list | None, incoming: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, tuple[int, ...], str | None]] = set()
    for evidence in [*(existing or []), *incoming]:
        key = (
            str(evidence.get("file", "")),
            tuple(evidence.get("lines", [])),
            evidence.get("commit"),
        )
        if key not in seen:
            seen.add(key)
            merged.append(evidence)
    return merged


def complete_analysis(
    db: Session,
    analysis: Analysis,
    repo: Repo,
    artifacts: AnalysisArtifacts,
) -> None:
    """Atomically store public artifacts and touched skill evidence."""
    if artifacts.analysis_mode == "full" or artifacts.changed_files:
        for question in db.scalars(
            select(QuestionRow).where(QuestionRow.repo_id == repo.id)
        ).all():
            db.delete(question)
    analysis.repo_map = artifacts.repo_map.model_dump(mode="json")
    analysis.findings = [finding.model_dump(mode="json") for finding in artifacts.findings]
    analysis.scores = artifacts.scores.model_dump(mode="json")
    analysis.stage = "done"
    analysis.progress = 100
    analysis.error = None

    for status in artifacts.scores.skills:
        row = db.scalar(
            select(SkillStatusRow).where(
                SkillStatusRow.user_id == repo.user_id,
                SkillStatusRow.repo_id == repo.id,
                SkillStatusRow.skill_id == status.skill_id,
            )
        )
        evidence = [item.model_dump(mode="json") for item in status.evidence]
        if row is None:
            row = SkillStatusRow(
                user_id=repo.user_id,
                repo_id=repo.id,
                skill_id=status.skill_id,
                tier=status.tier.value,
                evidence=evidence,
            )
            db.add(row)
        else:
            # Re-analysis may add evidence, but it must never erase a recall
            # promotion that has already moved this skill to verified.
            if row.tier != "verified":
                row.tier = status.tier.value
            row.evidence = _merge_evidence(row.evidence, evidence)

    db.commit()


INTERRUPTED = "The analysis was interrupted by a server restart. Run it again."


def fail_interrupted_analyses(db: Session) -> int:
    """Close every analysis a previous process left unfinished. Returns how many.

    The pipeline runs as a BackgroundTask, which dies with the process. A row
    still marked queued / cloning / scanning at STARTUP therefore has nobody
    working on it and never will -- but it would keep the status endpoint
    reporting "running", and keep `analyze` refusing a new run with 409, for
    ever. Only call this at startup: later on, a running row is genuinely running.
    """
    rows = db.scalars(select(Analysis).where(Analysis.stage.not_in(("done", "failed")))).all()
    for analysis in rows:
        analysis.stage = "failed"
        analysis.error = INTERRUPTED
    if rows:
        db.commit()
    return len(rows)


def fail_analysis(db: Session, analysis: Analysis, error: Exception | str) -> None:
    """Make failures visible to polling clients without exposing tracebacks."""
    analysis.stage = "failed"
    analysis.error = str(error)[:2_000]
    db.commit()
