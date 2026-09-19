"""Mock mode must serve the full happy path. If this fails, the demo is broken."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["mock_mode"] is True


def test_full_mock_journey():
    assert client.get("/repos").status_code == 200
    assert client.post("/repos/1/analyze").status_code == 202
    assert client.get("/repos/1/status").json()["stage"] == "done"
    assert client.get("/repos/1/scores").status_code == 200
    assert client.get("/repos/1/findings").status_code == 200
    assert client.get("/repos/1/questions").status_code == 200
    assert client.get("/repos/1/roadmap").status_code == 200
    assert client.get("/repos/1/code", params={"file": "app/x.py", "start": 1, "end": 5}).status_code == 200


def test_code_endpoint_rejects_path_traversal():
    """_safe_path is the one security-critical line in the backend."""
    from fastapi import HTTPException

    from app.routers.code import _safe_path

    try:
        _safe_path("demo-user", "repo", "../../../../etc/passwd")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("path traversal was not rejected")
