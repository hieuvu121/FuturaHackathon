"""GitHub OAuth. Owner: Track A."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..deps import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login() -> RedirectResponse:
    """Redirects to GitHub's authorize URL."""
    raise NotImplementedError("Track A: services/ingest/github.py authorize_url()")


@router.get("/callback")
def callback(code: str, request: Request) -> RedirectResponse:
    """Exchanges ?code for a token, stores it, issues a session."""
    raise NotImplementedError("Track A: services/ingest/github.py exchange_code()")


@router.get("/me")
def me(user: CurrentUser) -> dict[str, str | bool]:
    return {"user": user, "mock_mode": get_settings().mock_mode}
