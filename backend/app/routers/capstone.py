"""The roadmap's final stage: a project brief, a submission, and its review.

Mounted under the roadmap router (see the bottom of roadmap.py) rather than in
main.py, which no feature branch edits.

Submitting returns at once. Cloning and reviewing a repository takes a model
call and a network round trip, so it runs as a background task and the page
polls GET until the status leaves `reviewing`.
"""

from datetime import UTC, datetime, timedelta
import logging
from typing import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..deps import CurrentUser, DbDep
from ..models.db import CapstoneSubmissionRow, SessionLocal, User
from ..schemas.capstone import (
    CapstoneBrief,
    CapstoneReview,
    CapstoneState,
    CapstoneSubmission,
    CapstoneSubmit,
    SubmissionStatus,
)
from ..services.ingest import clone as clone_service
from ..services.roadmap.capstone import (
    build_brief,
    parse_repo_url,
    review_submission,
    sample_review,
)

router = APIRouter(prefix="/portfolio/capstone", tags=["roadmap"])
logger = logging.getLogger(__name__)

# A review still "in progress" after this long was orphaned by a restart.
STALE_AFTER = timedelta(minutes=10)


def _brief(user: str, db: Session) -> CapstoneBrief:
    # Imported here: roadmap.py mounts this router, so a top-level import would be circular.
    from .roadmap import portfolio_roadmap_graph

    return build_brief(portfolio_roadmap_graph(user, db))


def _owner(db: Session, login: str) -> User:
    owner = db.scalar(select(User).where(User.github_login == login))
    if owner is None:
        if not get_settings().mock_mode:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        # Mock mode has no OAuth round trip, so the demo user may not exist yet.
        owner = User(github_login=login)
        db.add(owner)
        db.commit()
        db.refresh(owner)
    return owner


def _latest(db: Session, owner: User) -> CapstoneSubmissionRow | None:
    return db.scalars(
        select(CapstoneSubmissionRow)
        .where(CapstoneSubmissionRow.user_id == owner.id)
        .order_by(CapstoneSubmissionRow.id.desc())
    ).first()


def _to_schema(row: CapstoneSubmissionRow) -> CapstoneSubmission:
    return CapstoneSubmission(
        id=row.id,
        repo_url=row.repo_url,
        notes=row.notes or "",
        status=SubmissionStatus(row.status),
        error=row.error,
        review=CapstoneReview.model_validate(row.review) if row.review else None,
        submitted_at=row.created_at,
    )


def run_review(
    submission_id: int,
    settings: Settings | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """Clone, review, store. Every failure ends as a `failed` row with a reason, never a stuck one."""
    settings = settings or get_settings()
    db = session_factory()
    try:
        row = db.get(CapstoneSubmissionRow, submission_id)
        if row is None:
            return
        brief = CapstoneBrief.model_validate(row.brief)
        owner = db.get(User, row.user_id)
        try:
            if settings.mock_mode:
                review = sample_review(brief)
            else:
                full_name = parse_repo_url(row.repo_url)
                # A separate cache namespace: reviewing must never replace the
                # clone an analysed portfolio repository is being read from.
                namespace = f"{owner.github_login}--capstone"
                root = clone_service.clone(settings, namespace, full_name, owner.github_token or "")
                try:
                    review = review_submission(settings, brief, root, row.notes or "")
                finally:
                    # A clone that will not delete is a housekeeping problem, and
                    # must not turn a finished review into a failed one.
                    try:
                        clone_service.cleanup_repo(settings, namespace, full_name)
                    except OSError:
                        logger.warning("Could not remove the capstone clone of %s", full_name)
            row.review = review.model_dump(mode="json")
            row.status = SubmissionStatus.REVIEWED.value
            row.error = None
        except Exception as exc:
            logger.warning("Capstone review failed for submission %s: %s", submission_id, exc)
            row.status = SubmissionStatus.FAILED.value
            row.error = _reason(exc)
        db.commit()
    finally:
        db.close()


def _reason(exc: Exception) -> str:
    """Something the user can act on, without leaking provider or filesystem detail."""
    if isinstance(exc, ValueError):
        return str(exc)
    if type(exc).__name__ == "GitCommandError":
        return "The repository could not be cloned. Check the URL and that your account can read it."
    if type(exc).__name__ in {"RateLimitError", "AuthenticationError", "PermissionDeniedError"}:
        return (
            "The AI reviewer is unavailable: the model provider refused the request "
            "(quota or credentials). Your repository was read successfully, so submit again "
            "once that is fixed."
        )
    return "The review could not be completed. Try submitting again in a moment."


@router.get("", response_model=CapstoneState)
def capstone(user: CurrentUser, db: DbDep) -> CapstoneState:
    """The brief for this user's roadmap, plus their latest submission if there is one."""
    row = _latest(db, _owner(db, user))
    return CapstoneState(brief=_brief(user, db), submission=_to_schema(row) if row else None)


@router.post("/submit", response_model=CapstoneState, status_code=status.HTTP_202_ACCEPTED)
def submit(
    payload: CapstoneSubmit, background: BackgroundTasks, user: CurrentUser, db: DbDep
) -> CapstoneState:
    try:
        parse_repo_url(payload.repo_url)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    owner = _owner(db, user)
    latest = _latest(db, owner)
    if latest is not None and latest.status == SubmissionStatus.REVIEWING.value:
        started = latest.created_at.replace(tzinfo=UTC) if latest.created_at else datetime.now(UTC)
        if datetime.now(UTC) - started < STALE_AFTER:
            raise HTTPException(status.HTTP_409_CONFLICT, "A review is already in progress")
        latest.status = SubmissionStatus.FAILED.value
        latest.error = "The review was interrupted. Submit again."
        db.commit()

    brief = _brief(user, db)
    row = CapstoneSubmissionRow(
        user_id=owner.id,
        repo_url=payload.repo_url.strip(),
        notes=payload.notes.strip(),
        status=SubmissionStatus.REVIEWING.value,
        brief=brief.model_dump(mode="json"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    background.add_task(run_review, row.id)
    return CapstoneState(brief=brief, submission=_to_schema(row))
