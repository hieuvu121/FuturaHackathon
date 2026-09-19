"""GitHub OAuth. Owner: Track A."""

import secrets

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from ..deps import CurrentUser, DbDep, SettingsDep
from ..models.db import User, init_db
from ..services.ingest import github

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(request: Request, settings: SettingsDep) -> RedirectResponse:
    """Redirects to GitHub's authorize URL."""
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    try:
        target = github.authorize_url(settings, state)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return RedirectResponse(target)


@router.get("/callback")
def callback(
    code: str,
    state: str,
    request: Request,
    settings: SettingsDep,
    db: DbDep,
) -> RedirectResponse:
    """Exchanges ?code for a token, stores it, issues a session."""
    expected_state = request.session.pop("oauth_state", None)
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state")

    try:
        token = github.exchange_code(settings, code)
        profile = github.get_user(token)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"GitHub OAuth failed: {exc}") from exc

    init_db()
    user = db.scalar(select(User).where(User.github_login == profile["login"]))
    if user is None:
        user = User(github_login=profile["login"])
        db.add(user)
    user.github_token = token
    user.email = profile.get("email")
    db.commit()

    request.session["user"] = user.github_login
    destination = f"{str(settings.cors_origins[0]).rstrip('/')}/connect"
    return RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/me")
def me(user: CurrentUser, settings: SettingsDep) -> dict[str, str | bool]:
    return {"user": user, "mock_mode": settings.mock_mode}
