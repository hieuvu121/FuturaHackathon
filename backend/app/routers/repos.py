"""Repository listing, selection, and pipeline kick-off. Owner: Track A."""

from fastapi import APIRouter, BackgroundTasks

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..mock_store import load

router = APIRouter(prefix="/repos", tags=["repos"])


@router.get("")
def list_repos(user: CurrentUser) -> list[dict]:
    """The user's repositories, for the 3-5 selection step."""
    if get_settings().mock_mode:
        return load("repos")
    raise NotImplementedError("Track A: services/ingest/github.py list_repos()")


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
