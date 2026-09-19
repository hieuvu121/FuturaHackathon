"""GitHub OAuth + API. Owner: Track A."""

from urllib.parse import urlencode

import httpx

from ...config import Settings

AUTHORIZE_ENDPOINT = "https://github.com/login/oauth/authorize"
TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
API_ENDPOINT = "https://api.github.com"
REQUEST_TIMEOUT = 20.0


def _require_oauth_config(settings: Settings) -> None:
    if not settings.github_client_id or not settings.github_client_secret:
        raise RuntimeError("GitHub OAuth credentials are not configured")


def authorize_url(settings: Settings, state: str) -> str:
    """The URL to redirect the user to."""
    _require_oauth_config(settings)
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "scope": "read:user user:email repo",
            "state": state,
        }
    )
    return f"{AUTHORIZE_ENDPOINT}?{query}"


def exchange_code(settings: Settings, code: str) -> str:
    """Trades ?code for an access token."""
    _require_oauth_config(settings)
    if not code.strip():
        raise ValueError("GitHub returned an empty authorization code")

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(
            TOKEN_ENDPOINT,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
        )
        response.raise_for_status()
        payload = response.json()

    token = payload.get("access_token")
    if not token:
        detail = payload.get("error_description") or payload.get("error") or "unknown response"
        raise RuntimeError(f"GitHub token exchange failed: {detail}")
    return str(token)


def get_user(token: str) -> dict:
    """Returns the authenticated GitHub user's stable identity."""
    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    ) as client:
        response = client.get(f"{API_ENDPOINT}/user")
        response.raise_for_status()
        payload = response.json()

    if not payload.get("login"):
        raise RuntimeError("GitHub user response did not include a login")
    return payload


def list_repos(token: str) -> list[dict]:
    """Repos with fork status and metadata attached -- filter.py needs is_fork."""
    repos: list[dict] = []
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT, headers=headers) as client:
        for page in range(1, 11):
            response = client.get(
                f"{API_ENDPOINT}/user/repos",
                params={
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "pushed",
                    "direction": "desc",
                    "per_page": 100,
                    "page": page,
                },
            )
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list):
                raise RuntimeError("GitHub repositories response was not a list")

            repos.extend(
                {
                    "id": str(repo["id"]),
                    "full_name": repo["full_name"],
                    "language": repo.get("language"),
                    "is_fork": bool(repo.get("fork", False)),
                    "stars": int(repo.get("stargazers_count", 0)),
                    "pushed_at": repo.get("pushed_at"),
                    "clone_url": repo.get("clone_url"),
                    "default_branch": repo.get("default_branch", "main"),
                    "private": bool(repo.get("private", False)),
                }
                for repo in batch
            )
            if len(batch) < 100:
                break

    return repos
