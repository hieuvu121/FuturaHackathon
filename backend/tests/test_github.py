"""Offline tests for GitHub OAuth and repository API translation."""

from urllib.parse import parse_qs, urlparse

import pytest

from app.config import Settings
from app.services.ingest import github


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, *, post_payload=None, get_payloads=None):
        self.post_payload = post_payload
        self.get_payloads = iter(get_payloads or [])
        self.posts = []
        self.gets = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse(self.post_payload)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return FakeResponse(next(self.get_payloads))


def _settings() -> Settings:
    return Settings(
        github_client_id="client-id",
        github_client_secret="client-secret",
        github_redirect_uri="http://localhost:8000/auth/callback",
    )


def test_authorize_url_contains_callback_scopes_and_csrf_state():
    url = github.authorize_url(_settings(), "csrf-state")
    query = parse_qs(urlparse(url).query)

    assert url.startswith(github.AUTHORIZE_ENDPOINT)
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == ["http://localhost:8000/auth/callback"]
    assert query["state"] == ["csrf-state"]
    assert set(query["scope"][0].split()) == {"read:user", "user:email", "repo"}


def test_authorize_url_requires_credentials():
    with pytest.raises(RuntimeError, match="credentials"):
        github.authorize_url(Settings(github_client_id="", github_client_secret=""), "state")


def test_exchange_code_returns_token(monkeypatch):
    client = FakeClient(post_payload={"access_token": "token-123"})
    monkeypatch.setattr(github.httpx, "Client", lambda **kwargs: client)

    assert github.exchange_code(_settings(), "code-123") == "token-123"
    assert client.posts[0][0] == github.TOKEN_ENDPOINT
    assert client.posts[0][1]["data"]["code"] == "code-123"


def test_exchange_code_rejects_error_payload(monkeypatch):
    client = FakeClient(post_payload={"error": "bad_verification_code"})
    monkeypatch.setattr(github.httpx, "Client", lambda **kwargs: client)

    with pytest.raises(RuntimeError, match="bad_verification_code"):
        github.exchange_code(_settings(), "expired")


def test_get_user_requires_a_login(monkeypatch):
    client = FakeClient(get_payloads=[{"id": 1}])
    monkeypatch.setattr(github.httpx, "Client", lambda **kwargs: client)

    with pytest.raises(RuntimeError, match="login"):
        github.get_user("token")


def test_list_repos_normalises_github_fields(monkeypatch):
    raw_repo = {
        "id": 42,
        "full_name": "developer/project",
        "language": "Python",
        "fork": True,
        "stargazers_count": 7,
        "pushed_at": "2026-09-19T00:00:00Z",
        "clone_url": "https://github.com/developer/project.git",
        "default_branch": "trunk",
        "private": False,
    }
    client = FakeClient(get_payloads=[[raw_repo]])
    monkeypatch.setattr(github.httpx, "Client", lambda **kwargs: client)

    assert github.list_repos("token") == [
        {
            "id": "42",
            "full_name": "developer/project",
            "language": "Python",
            "is_fork": True,
            "stars": 7,
            "pushed_at": "2026-09-19T00:00:00Z",
            "clone_url": "https://github.com/developer/project.git",
            "default_branch": "trunk",
            "private": False,
        }
    ]
    assert client.gets[0][1]["params"]["per_page"] == 100
