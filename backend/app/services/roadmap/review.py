"""The user's standing with their roadmap: the recall session behind it, and whether they agree.

A recall session is five questions. Its answers build the roadmap, the roadmap
is shown, and the user either accepts it or disputes it. Disputing has two
ways out -- sit the test again, or edit the roadmap by hand -- and both end in
the same place: an accepted roadmap.

Nothing is ever deleted to make that work. Redoing the test raises a floor in
the attempt log, so earlier answers simply stop counting.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models.db import RecallAttemptRow, RoadmapReviewRow
from ...schemas.roadmap import ReviewStatus, RoadmapReview

SESSION_LENGTH = 5


def review_row(db: Session, user_id: int) -> RoadmapReviewRow:
    row = db.get(RoadmapReviewRow, user_id)
    if row is None:
        row = RoadmapReviewRow(
            user_id=user_id, status=ReviewStatus.PENDING.value, recall_floor=0, hidden_skills=[]
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def session_attempts(db: Session, user_id: int) -> list[RecallAttemptRow]:
    """The answers that count: those given since the test was last restarted."""
    floor = review_row(db, user_id).recall_floor
    return list(
        db.scalars(
            select(RecallAttemptRow)
            .where(RecallAttemptRow.user_id == user_id, RecallAttemptRow.id > floor)
            .order_by(RecallAttemptRow.id)
        ).all()
    )


def recall_levels(db: Session, user_id: int) -> dict[str, tuple[set[int], set[int]]]:
    """skill_id -> (drill levels passed, drill levels failed) in the current session."""
    levels: dict[str, tuple[set[int], set[int]]] = {}
    for attempt in session_attempts(db, user_id):
        levels.setdefault(attempt.skill_id, (set(), set()))[0 if attempt.passed else 1].add(
            attempt.level
        )
    return levels


def _touch(db: Session, row: RoadmapReviewRow) -> RoadmapReviewRow:
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row


def mark_pending(db: Session, user_id: int) -> RoadmapReviewRow:
    """A finished recall session redraws the roadmap, so it needs agreeing to again."""
    row = review_row(db, user_id)
    row.status = ReviewStatus.PENDING.value
    return _touch(db, row)


def accept(db: Session, user_id: int) -> RoadmapReviewRow:
    row = review_row(db, user_id)
    row.status = ReviewStatus.ACCEPTED.value
    return _touch(db, row)


def restart_recall(db: Session, user_id: int) -> RoadmapReviewRow:
    """Dispute by retesting: every answer so far stops counting."""
    row = review_row(db, user_id)
    latest = db.scalar(
        select(func.max(RecallAttemptRow.id)).where(RecallAttemptRow.user_id == user_id)
    )
    row.recall_floor = latest or 0
    row.status = ReviewStatus.PENDING.value
    return _touch(db, row)


def set_hidden(db: Session, user_id: int, skill_ids: list[str]) -> RoadmapReviewRow:
    """Dispute by editing: these skills leave the roadmap until the user brings them back."""
    row = review_row(db, user_id)
    row.hidden_skills = sorted({skill_id.strip() for skill_id in skill_ids if skill_id.strip()})
    row.status = ReviewStatus.PENDING.value
    return _touch(db, row)


def to_schema(db: Session, row: RoadmapReviewRow) -> RoadmapReview:
    return RoadmapReview(
        status=ReviewStatus(row.status),
        hidden_skills=list(row.hidden_skills or []),
        recall_answered=min(len(session_attempts(db, row.user_id)), SESSION_LENGTH),
        recall_session_length=SESSION_LENGTH,
    )
