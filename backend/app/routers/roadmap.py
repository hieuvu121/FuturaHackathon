"""The three buckets. Owner: Track D."""

from fastapi import APIRouter

from ..config import get_settings
from ..deps import CurrentUser
from ..mock_store import load
from ..schemas.roadmap import Buckets

router = APIRouter(prefix="/repos", tags=["roadmap"])


@router.get("/{repo_id}/roadmap", response_model=Buckets)
def roadmap(repo_id: str, user: CurrentUser, role: str = "backend", region: str = "AU") -> Buckets:
    """Must return sensible output even when market frequency is None."""
    if get_settings().mock_mode:
        return Buckets.model_validate(load("roadmap"))
    raise NotImplementedError("Track D: matcher.py -> buckets.py")
