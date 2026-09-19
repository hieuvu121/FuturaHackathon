"""Accepting or disputing the roadmap.

Mounted under the roadmap router (see the bottom of roadmap.py) rather than in
main.py, which no feature branch edits.

  GET  /repos/portfolio/roadmap/review          where things stand
  POST /repos/portfolio/roadmap/review/accept   "this is me"
  POST /repos/portfolio/roadmap/review/redo     dispute: sit the recall test again
  POST /repos/portfolio/roadmap/review/tailor   dispute: edit the roadmap by hand
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..models.db import User
from ..schemas.roadmap import RoadmapReview, TailorRequest
from ..services.roadmap import review

router = APIRouter(prefix="/portfolio/roadmap/review", tags=["roadmap"])


def owner_of(db: Session, login: str) -> User:
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


@router.get("", response_model=RoadmapReview)
def current(user: CurrentUser, db: DbDep) -> RoadmapReview:
    return review.to_schema(db, review.review_row(db, owner_of(db, user).id))


@router.post("/accept", response_model=RoadmapReview)
def accept(user: CurrentUser, db: DbDep) -> RoadmapReview:
    return review.to_schema(db, review.accept(db, owner_of(db, user).id))


@router.post("/redo", response_model=RoadmapReview)
def redo(user: CurrentUser, db: DbDep) -> RoadmapReview:
    """Start a fresh recall session. Earlier answers are kept but no longer count."""
    return review.to_schema(db, review.restart_recall(db, owner_of(db, user).id))


@router.post("/tailor", response_model=RoadmapReview)
def tailor(payload: TailorRequest, user: CurrentUser, db: DbDep) -> RoadmapReview:
    """Replace the set of skills the user has removed from their roadmap."""
    return review.to_schema(db, review.set_hidden(db, owner_of(db, user).id, payload.hidden_skills))
