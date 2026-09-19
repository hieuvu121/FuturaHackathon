"""Serves scores.json and findings.json. Owner: Track B."""

from fastapi import APIRouter

from ..config import get_settings
from ..deps import CurrentUser
from ..mock_store import load
from ..schemas.findings import Finding
from ..schemas.scores import Scores

router = APIRouter(prefix="/repos", tags=["analysis"])


@router.get("/{repo_id}/scores", response_model=Scores)
def scores(repo_id: str, user: CurrentUser) -> Scores:
    if get_settings().mock_mode:
        return Scores.model_validate(load("scores"))
    raise NotImplementedError("Track B: services/analyze/scorer.py")


@router.get("/{repo_id}/findings", response_model=list[Finding])
def findings(repo_id: str, user: CurrentUser) -> list[Finding]:
    """Validated findings only. Anything validator.py dropped never reaches here."""
    if get_settings().mock_mode:
        return [Finding.model_validate(f) for f in load("findings")]
    raise NotImplementedError("Track B: services/analyze/validator.py output")
