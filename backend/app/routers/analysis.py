"""Serves scores.json and findings.json. Owner: Track B."""

from fastapi import APIRouter, HTTPException, status

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..mock_store import load
from ..schemas.findings import Finding
from ..schemas.scores import Scores
from ..schemas.portfolio import PortfolioProfile
from ..services.portfolio import build_profile
from ..services.storage import get_owned_repo, latest_analysis

router = APIRouter(prefix="/repos", tags=["analysis"])


@router.get("/portfolio/profile", response_model=PortfolioProfile)
def portfolio_profile(user: CurrentUser, db: DbDep) -> PortfolioProfile:
    if get_settings().mock_mode:
        raise HTTPException(status.HTTP_409_CONFLICT, "Portfolio profile requires live mode")
    try:
        return build_profile(db, user)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/{repo_id}/scores", response_model=Scores)
def scores(repo_id: str, user: CurrentUser, db: DbDep) -> Scores:
    if get_settings().mock_mode:
        return Scores.model_validate(load("scores"))
    repo = get_owned_repo(db, repo_id, user)
    analysis = latest_analysis(db, repo.id) if repo is not None else None
    if analysis is None or analysis.scores is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository scores not found")
    return Scores.model_validate(analysis.scores)


@router.get("/{repo_id}/findings", response_model=list[Finding])
def findings(repo_id: str, user: CurrentUser, db: DbDep) -> list[Finding]:
    """Validated findings only. Anything validator.py dropped never reaches here."""
    if get_settings().mock_mode:
        return [Finding.model_validate(f) for f in load("findings")]
    repo = get_owned_repo(db, repo_id, user)
    analysis = latest_analysis(db, repo.id) if repo is not None else None
    if analysis is None or analysis.findings is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository findings not found")
    return [Finding.model_validate(finding) for finding in analysis.findings]
