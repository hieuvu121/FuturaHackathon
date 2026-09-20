"""Repository listing, selection, and pipeline kick-off. Owner: Track A."""

import httpx
from fastapi import APIRouter, BackgroundTasks
from fastapi import HTTPException, status as http_status
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..mock_store import load
from ..models.db import Repo, User, init_db
from ..schemas.repo_map import RepoMap
from ..schemas.portfolio import (
    PortfolioRepoSummary,
    PortfolioSelectionRequest,
    PortfolioSelectionResponse,
)
from ..services.ingest.github import list_repos as list_github_repos
from ..services.pipeline import run_analysis_task
from ..services.portfolio import owned_selected_repos, replace_selection, selection_summaries
from ..services.storage import get_owned_repo, latest_analysis, start_analysis

router = APIRouter(prefix="/repos", tags=["repos"])


@router.get("/portfolio", response_model=PortfolioSelectionResponse)
def get_portfolio(user: CurrentUser, db: DbDep) -> PortfolioSelectionResponse:
    if get_settings().mock_mode:
        repos = load("repos")[:3]
        return PortfolioSelectionResponse(
            repositories=[
                PortfolioRepoSummary(
                    id=str(repo["id"]),
                    full_name=repo["full_name"],
                    language=repo.get("language"),
                    stage="done",
                    progress=100,
                )
                for repo in repos
            ]
        )
    return PortfolioSelectionResponse(
        repositories=selection_summaries(db, owned_selected_repos(db, user))
    )


@router.put("/portfolio", response_model=PortfolioSelectionResponse)
def set_portfolio(
    selection: PortfolioSelectionRequest,
    user: CurrentUser,
    db: DbDep,
) -> PortfolioSelectionResponse:
    if get_settings().mock_mode:
        return get_portfolio(user, db)
    try:
        repos = replace_selection(db, user, selection.repo_ids)
    except ValueError as exc:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return PortfolioSelectionResponse(repositories=selection_summaries(db, repos))


@router.get("")
def list_repos(user: CurrentUser, db: DbDep) -> list[dict]:
    """The user's repositories, for the 3-5 selection step."""
    if get_settings().mock_mode:
        return load("repos")

    init_db()
    owner = db.scalar(select(User).where(User.github_login == user))
    if owner is None or not owner.github_token:
        raise HTTPException(http_status.HTTP_401_UNAUTHORIZED, "GitHub account is not connected")

    try:
        github_repos = list_github_repos(owner.github_token)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            # GitHub no longer accepts the stored token: it was revoked, it expired, or
            # the OAuth app's secret changed. Keeping it would fail the same way on every
            # request, so drop it and answer 401 -- which the Connect page already turns
            # into a "Connect GitHub" link -- instead of crashing with a 500.
            owner.github_token = None
            db.commit()
            raise HTTPException(
                http_status.HTTP_401_UNAUTHORIZED,
                "Your GitHub connection has expired. Connect GitHub again to continue.",
            ) from exc
        raise HTTPException(
            http_status.HTTP_502_BAD_GATEWAY, "GitHub could not list your repositories right now."
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            http_status.HTTP_502_BAD_GATEWAY, "GitHub could not be reached. Try again in a moment."
        ) from exc
    for payload in github_repos:
        repo_id = int(payload["id"])
        repo = db.get(Repo, repo_id)
        if repo is None:
            repo = Repo(id=repo_id, user_id=owner.id, full_name=payload["full_name"])
            db.add(repo)
        repo.user_id = owner.id
        repo.full_name = payload["full_name"]
        repo.language = payload.get("language")
        repo.is_fork = payload["is_fork"]
    db.commit()
    return github_repos


@router.post("/{repo_id}/analyze", status_code=202)
def analyze(
    repo_id: str,
    tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbDep,
) -> dict[str, str | int]:
    """Queues INGEST -> ANALYZE as a BackgroundTask and returns immediately."""
    settings = get_settings()
    if settings.mock_mode:
        return {"repo_id": repo_id, "status": "queued"}
    repo = get_owned_repo(db, repo_id, user)
    if repo is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Repository not found")
    current = latest_analysis(db, repo.id)
    if current is not None and current.stage not in {"done", "failed"}:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Repository analysis is already running")

    analysis = start_analysis(db, repo)
    tasks.add_task(run_analysis_task, settings, analysis.id)
    return {"repo_id": repo_id, "analysis_id": analysis.id, "status": "queued"}


@router.get("/{repo_id}/status")
def status(repo_id: str, user: CurrentUser, db: DbDep) -> dict[str, str | int | None]:
    """Polled by the frontend while the pipeline runs."""
    if get_settings().mock_mode:
        return {"repo_id": repo_id, "stage": "done", "progress": 100}
    repo = get_owned_repo(db, repo_id, user)
    if repo is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Repository not found")
    analysis = latest_analysis(db, repo.id)
    if analysis is None:
        return {"repo_id": repo_id, "stage": "not_started", "progress": 0, "error": None}
    return {
        "repo_id": repo_id,
        "stage": analysis.stage,
        "progress": analysis.progress,
        "error": analysis.error,
    }


@router.get("/{repo_id}/repo_map", response_model=RepoMap)
def repo_map(repo_id: str, user: CurrentUser, db: DbDep) -> dict:
    if get_settings().mock_mode:
        return load("repo_map")
    repo = get_owned_repo(db, repo_id, user)
    analysis = latest_analysis(db, repo.id) if repo is not None else None
    if analysis is None or analysis.repo_map is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Repository analysis not found")
    return analysis.repo_map
