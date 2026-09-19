"""GitHub OAuth + API. Owner: Track A."""

from ...config import Settings


def authorize_url(settings: Settings, state: str) -> str:
    """The URL to redirect the user to."""
    raise NotImplementedError


def exchange_code(settings: Settings, code: str) -> str:
    """Trades ?code for an access token."""
    raise NotImplementedError


def list_repos(token: str) -> list[dict]:
    """Repos with fork status and metadata attached -- filter.py needs is_fork."""
    raise NotImplementedError
