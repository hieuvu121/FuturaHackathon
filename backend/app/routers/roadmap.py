"""The three buckets. Owner: Track D."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..mock_store import load
from ..models.db import SkillStatusRow
from ..schemas.scores import SkillStatus
from ..schemas.roadmap import Buckets
from ..services.knowledge import get_demand, get_taxonomy
from ..services.roadmap.buckets import build
from ..services.roadmap.matcher import match
from ..services.storage import get_owned_repo

router = APIRouter(prefix="/repos", tags=["roadmap"])


@router.get("/{repo_id}/roadmap", response_model=Buckets)
def roadmap(
    repo_id: str,
    user: CurrentUser,
    db: DbDep,
    role: str = "backend",
    region: str = "AU",
) -> Buckets:
    """Must return sensible output even when market frequency is None."""
    settings = get_settings()
    if settings.mock_mode:
        return Buckets.model_validate(load("roadmap"))
    repo = get_owned_repo(db, repo_id, user)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    rows = db.scalars(
        select(SkillStatusRow).where(
            SkillStatusRow.user_id == repo.user_id,
            SkillStatusRow.repo_id == repo.id,
        )
    ).all()
    skills = [
        SkillStatus.model_validate(
            {"skill_id": row.skill_id, "tier": row.tier, "evidence": row.evidence or []}
        )
        for row in rows
    ]
    taxonomy = get_taxonomy(settings)
    demand = match(skills, taxonomy, get_demand(settings), role, region)
    return build(skills, demand, role, region, taxonomy)
