"""Repository listing, selection, and pipeline kick-off. Owner: Track A."""

from fastapi import APIRouter, BackgroundTasks
from fastapi import HTTPException, status
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..mock_store import load
from ..models.db import Repo, User, init_db
from ..services.ingest.github import list_repos as list_github_repos

router = APIRouter(prefix="/repos", tags=["repos"])


@router.get("")
def list_repos(user: CurrentUser, db: DbDep) -> list[dict]:
    """The user's repositories, for the 3-5 selection step."""
    if get_settings().mock_mode:
        return load("repos")

    init_db()
    owner = db.scalar(select(User).where(User.github_login == user))
    if owner is None or not owner.github_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub account is not connected")

    github_repos = list_github_repos(owner.github_token)
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
def analyze(repo_id: str, tasks: BackgroundTasks, user: CurrentUser, db: DbDep) -> dict[str, str]:
    """Queues INGEST -> ANALYZE as a BackgroundTask and returns immediately."""
    if get_settings().mock_mode:
        return {"repo_id": repo_id, "status": "queued"}
    raise NotImplementedError("Track A: tasks.add_task(run_pipeline, repo_id, user)")


@router.get("/{repo_id}/status")
def status(repo_id: str, user: CurrentUser) -> dict[str, str | int]:
    """Polled by the frontend while the pipeline runs."""
    if get_settings().mock_mode:
        return {"repo_id": repo_id, "stage": "done", "progress": 100}
    raise NotImplementedError("Track A: read the analyses table")


@router.get("/{repo_id}/repo_map")
def repo_map(repo_id: str, user: CurrentUser) -> dict:
    if get_settings().mock_mode:
        return load("repo_map")
    raise NotImplementedError("Track A: read the persisted RepoMap")
