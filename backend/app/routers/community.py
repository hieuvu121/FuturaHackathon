"""Community: shared roadmaps and the reviews they collect.

  GET    /community/roadmaps                 everything shared, newest first
  POST   /community/roadmaps                 share a snapshot of your roadmap under a role title
  GET    /community/roadmaps/{id}            one roadmap with its reviews
  DELETE /community/roadmaps/{id}            take your own roadmap down
  POST   /community/roadmaps/{id}/comments   review it: validate, suggest, or just comment
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..models.db import CommunityCommentRow, CommunityRoadmapRow, User
from ..schemas.community import (
    CommunityRoadmap,
    CommunityRoadmapDetail,
    NewComment,
    ShareRoadmap,
)
from ..services import community

router = APIRouter(prefix="/community", tags=["community"])


def _viewer(db: Session, login: str) -> User:
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


def _roadmap(db: Session, roadmap_id: int) -> CommunityRoadmapRow:
    row = db.get(CommunityRoadmapRow, roadmap_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roadmap not found")
    return row


@router.get("/roadmaps", response_model=list[CommunityRoadmap])
def list_roadmaps(user: CurrentUser, db: DbDep) -> list[CommunityRoadmap]:
    settings = get_settings()
    community.ensure_samples(db, settings)
    viewer = _viewer(db, user)
    # Real roadmaps newest first; the samples trail them however late they were seeded.
    rows = db.scalars(
        select(CommunityRoadmapRow).order_by(CommunityRoadmapRow.is_sample, CommunityRoadmapRow.id.desc())
    ).all()
    return [community.to_roadmap(db, settings, row, viewer) for row in rows]


@router.post("/roadmaps", response_model=CommunityRoadmapDetail, status_code=status.HTTP_201_CREATED)
def share_roadmap(payload: ShareRoadmap, user: CurrentUser, db: DbDep) -> CommunityRoadmapDetail:
    """Share the caller's roadmap as it stands right now."""
    # Imported here to keep this router free of the roadmap router's import chain.
    from .roadmap import portfolio_roadmap_graph

    settings = get_settings()
    viewer = _viewer(db, user)
    stages, overall = community.snapshot(portfolio_roadmap_graph(user, db))
    if not stages:
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no roadmap to share yet")
    row = CommunityRoadmapRow(
        user_id=viewer.id,
        title=" ".join(payload.title.split()),
        summary=" ".join(payload.summary.split()),
        stages=stages,
        overall=overall,
        is_sample=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return community.to_detail(db, settings, row, viewer)


@router.get("/roadmaps/{roadmap_id}", response_model=CommunityRoadmapDetail)
def read_roadmap(roadmap_id: int, user: CurrentUser, db: DbDep) -> CommunityRoadmapDetail:
    return community.to_detail(db, get_settings(), _roadmap(db, roadmap_id), _viewer(db, user))


@router.delete("/roadmaps/{roadmap_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_roadmap(roadmap_id: int, user: CurrentUser, db: DbDep) -> None:
    row = _roadmap(db, roadmap_id)
    if row.user_id is None or row.user_id != _viewer(db, user).id:
        # 404 rather than 403: whether someone else's roadmap exists is already
        # public, but there is no reason to confirm what the caller may not do.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roadmap not found")
    db.execute(delete(CommunityCommentRow).where(CommunityCommentRow.roadmap_id == row.id))
    db.delete(row)
    db.commit()


@router.post(
    "/roadmaps/{roadmap_id}/comments",
    response_model=CommunityRoadmapDetail,
    status_code=status.HTTP_201_CREATED,
)
def comment(roadmap_id: int, payload: NewComment, user: CurrentUser, db: DbDep) -> CommunityRoadmapDetail:
    settings = get_settings()
    row = _roadmap(db, roadmap_id)
    viewer = _viewer(db, user)
    if not payload.body.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Write something first")
    community.add_comment(db, settings, row, viewer, payload.body, payload.verdict)
    return community.to_detail(db, settings, row, viewer)
