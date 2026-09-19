"""Background pipeline and queueing tests."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models.db import Analysis, Base, Repo, User
from app.routers import repos as repos_router
from app.schemas.repo_map import RepoMap
from app.schemas.scores import Scores
from app.services import pipeline
from app.services.analyze import AnalysisArtifacts
from app.services.storage import start_analysis


@pytest.fixture
def session_factory(tmp_path: Path) -> Callable[[], Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pipeline.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _seed(session_factory) -> tuple[int, int]:
    with session_factory() as db:
        owner = User(
            id=1,
            github_login="developer",
            github_token="github-token",
            email="developer@example.com",
        )
        repo = Repo(
            id=10,
            user_id=1,
            full_name="owner/project",
            language="Python",
            is_fork=False,
        )
        db.add_all([owner, repo])
        db.commit()
        analysis = start_analysis(db, repo)
        return repo.id, analysis.id


def _artifacts() -> AnalysisArtifacts:
    repo_map = RepoMap(
        repo="owner/project",
        language="python",
        analyzed_at=datetime.now(UTC),
        total_files=0,
    )
    return AnalysisArtifacts(
        repo_map=repo_map,
        findings=[],
        dropped_findings=[],
        scores=Scores(repo="owner/project"),
        repository_metrics={},
    )


def test_background_worker_reports_progress_and_persists_success(
    tmp_path: Path, session_factory, monkeypatch
):
    repo_id, analysis_id = _seed(session_factory)
    reports: list[tuple[str, int]] = []

    def fake_analyze(settings, user, repo_full_name, token, **kwargs):
        assert (user, repo_full_name, token) == (
            "developer",
            "owner/project",
            "github-token",
        )
        for update in [("ingesting", 5), ("scanning", 35), ("scoring", 80), ("persisting", 95)]:
            kwargs["progress"](*update)
            reports.append(update)
        return _artifacts()

    monkeypatch.setattr(pipeline, "analyze_repository", fake_analyze)
    settings = Settings(cache_dir=tmp_path / "cache")

    pipeline.run_analysis_task(settings, analysis_id, session_factory)

    with session_factory() as db:
        analysis = db.get(Analysis, analysis_id)
        repo = db.get(Repo, repo_id)
        assert analysis.stage == "done"
        assert analysis.progress == 100
        assert analysis.repo_map["repo"] == "owner/project"
        assert repo.clone_path == str(settings.cache_dir / "developer" / "project")
    assert reports[-1] == ("persisting", 95)


def test_background_worker_marks_failure_and_cleans_partial_clone(
    tmp_path: Path, session_factory, monkeypatch
):
    _, analysis_id = _seed(session_factory)
    cleaned: list[tuple[str, str]] = []

    def fail(*args, **kwargs):
        kwargs["progress"]("scanning", 35)
        raise RuntimeError("provider failed")

    monkeypatch.setattr(pipeline, "analyze_repository", fail)
    monkeypatch.setattr(
        pipeline.clone_service,
        "cleanup_repo",
        lambda settings, user, repo: cleaned.append((user, repo)),
    )

    pipeline.run_analysis_task(Settings(cache_dir=tmp_path / "cache"), analysis_id, session_factory)

    with session_factory() as db:
        analysis = db.get(Analysis, analysis_id)
        assert analysis.stage == "failed"
        assert analysis.progress == 35
        assert analysis.error == "provider failed"
    assert cleaned == [("developer", "owner/project")]


class FakeTasks:
    def __init__(self):
        self.calls = []

    def add_task(self, function, *args):
        self.calls.append((function, args))


def test_analyze_endpoint_queues_owned_repo(session_factory, monkeypatch):
    repo_id, existing_analysis_id = _seed(session_factory)
    with session_factory() as db:
        existing = db.get(Analysis, existing_analysis_id)
        existing.stage = "done"
        db.commit()
        tasks = FakeTasks()
        settings = Settings(mock_mode=False)
        monkeypatch.setattr(repos_router, "get_settings", lambda: settings)

        response = repos_router.analyze(str(repo_id), tasks, "developer", db)

        assert response["status"] == "queued"
        assert response["analysis_id"] != existing_analysis_id
        assert tasks.calls == [
            (repos_router.run_analysis_task, (settings, response["analysis_id"]))
        ]
        assert repos_router.run_analysis_task is pipeline.run_analysis_task


def test_analyze_endpoint_rejects_duplicate_active_run(session_factory, monkeypatch):
    repo_id, _ = _seed(session_factory)
    monkeypatch.setattr(repos_router, "get_settings", lambda: Settings(mock_mode=False))

    with session_factory() as db, pytest.raises(HTTPException) as error:
        repos_router.analyze(str(repo_id), FakeTasks(), "developer", db)

    assert error.value.status_code == 409
