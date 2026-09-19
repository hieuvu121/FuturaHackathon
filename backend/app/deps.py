"""Shared FastAPI dependencies.

Owner: Track A (ingest/auth). Other tracks consume these, do not edit them.
"""

from typing import Annotated, Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models.db import Repo, SessionLocal, User

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, settings: SettingsDep) -> str:
    """Returns the GitHub login of the session user.

    In mock mode there is no OAuth round trip, so a fixed demo user is used.
    """
    if settings.mock_mode:
        return "demo-user"
    user = request.session.get("user")
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[str, Depends(get_current_user)]


def verify_repo_access(repo_id: str, user: CurrentUser, db: DbDep) -> str:
    """Confirms the session user owns/selected this repo. Returns repo_id."""
    try:
        numeric_repo_id = int(repo_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found") from exc

    repo = db.scalar(
        select(Repo)
        .join(User, Repo.user_id == User.id)
        .where(Repo.id == numeric_repo_id, User.github_login == user)
    )
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    return repo_id
