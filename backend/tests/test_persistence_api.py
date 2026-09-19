"""Persistence and real-mode API read tests."""

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.models.db import Analysis, Base, Repo, SkillStatusRow, User
from app.routers import analysis as analysis_router
from app.routers import repos as repos_router
from app.schemas.findings import Finding
from app.schemas.repo_map import FunctionNode, RepoMap
from app.schemas.scores import DimensionScore, Scores, SkillStatus, Tier
from app.services.analyze import AnalysisArtifacts
from app.services.storage import complete_analysis, start_analysis


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def owned_repo(db: Session) -> Repo:
    user = User(id=1, github_login="developer", github_token="token")
    repo = Repo(id=10, user_id=1, full_name="owner/project", language="Python")
    db.add_all([user, repo])
    db.commit()
    return repo


def _artifacts() -> AnalysisArtifacts:
    evidence = {"file": "app.py", "lines": [1, 2], "commit": "abc123"}
    finding = Finding.model_validate(
        {
            "id": "grounded",
            "dimension": "code_structure",
            "severity": "medium",
            "observation": "Grounded observation.",
            "evidence": evidence,
            "confidence": 0.9,
        }
    )
    repo_map = RepoMap(
        repo="owner/project",
        language="python",
        analyzed_at=datetime.now(UTC),
        total_files=1,
        functions=[
            FunctionNode(
                name="run",
                file="app.py",
                lines=(1, 2),
                complexity=1,
                loc=2,
            )
        ],
    )
    scores = Scores(
        repo="owner/project",
        dimensions=[
            DimensionScore(
                dimension="code_structure",
                level=3,
                rationale="Evidence-backed.",
                evidence=[finding.evidence],
            )
        ],
        skills=[
            SkillStatus(skill_id="python", tier=Tier.TOUCHED, evidence=[finding.evidence])
        ],
    )
    return AnalysisArtifacts(
        repo_map=repo_map,
        findings=[finding],
        dropped_findings=[],
        scores=scores,
        repository_metrics={},
    )


def test_complete_analysis_persists_json_and_touched_skills(db: Session, owned_repo: Repo):
    analysis = start_analysis(db, owned_repo)

    complete_analysis(db, analysis, owned_repo, _artifacts())

    stored = db.get(Analysis, analysis.id)
    assert stored.stage == "done"
    assert stored.progress == 100
    assert stored.repo_map["analyzed_at"].endswith("Z")
    assert [item["id"] for item in stored.findings] == ["grounded"]
    assert stored.scores["repo"] == "owner/project"
    skill = db.scalar(select(SkillStatusRow).where(SkillStatusRow.repo_id == owned_repo.id))
    assert skill.skill_id == "python"
    assert skill.tier == "touched"
    assert skill.evidence[0]["file"] == "app.py"


def test_reanalysis_never_downgrades_verified_skill(db: Session, owned_repo: Repo):
    db.add(
        SkillStatusRow(
            user_id=owned_repo.user_id,
            repo_id=owned_repo.id,
            skill_id="python",
            tier="verified",
            evidence=[],
        )
    )
    db.commit()

    complete_analysis(db, start_analysis(db, owned_repo), owned_repo, _artifacts())

    skill = db.scalar(select(SkillStatusRow).where(SkillStatusRow.repo_id == owned_repo.id))
    assert skill.tier == "verified"
    assert skill.evidence[0]["file"] == "app.py"


def test_real_mode_read_endpoints_return_latest_owned_analysis(
    db: Session, owned_repo: Repo, monkeypatch
):
    first = start_analysis(db, owned_repo)
    first.stage = "failed"
    db.commit()
    latest = start_analysis(db, owned_repo)
    complete_analysis(db, latest, owned_repo, _artifacts())
    real_settings = Settings(mock_mode=False)
    monkeypatch.setattr(repos_router, "get_settings", lambda: real_settings)
    monkeypatch.setattr(analysis_router, "get_settings", lambda: real_settings)

    status_payload = repos_router.status("10", "developer", db)
    repo_map_payload = repos_router.repo_map("10", "developer", db)
    findings_payload = analysis_router.findings("10", "developer", db)
    scores_payload = analysis_router.scores("10", "developer", db)

    assert status_payload["stage"] == "done"
    assert repo_map_payload["repo"] == "owner/project"
    assert [finding.id for finding in findings_payload] == ["grounded"]
    assert scores_payload.repo == "owner/project"


def test_real_mode_reads_do_not_leak_another_users_analysis(
    db: Session, owned_repo: Repo, monkeypatch
):
    complete_analysis(db, start_analysis(db, owned_repo), owned_repo, _artifacts())
    real_settings = Settings(mock_mode=False)
    monkeypatch.setattr(repos_router, "get_settings", lambda: real_settings)
    monkeypatch.setattr(analysis_router, "get_settings", lambda: real_settings)

    with pytest.raises(HTTPException) as repo_error:
        repos_router.repo_map("10", "intruder", db)
    with pytest.raises(HTTPException) as score_error:
        analysis_router.scores("10", "intruder", db)

    assert repo_error.value.status_code == 404
    assert score_error.value.status_code == 404
