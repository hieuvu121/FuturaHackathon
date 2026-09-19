"""Portfolio selection, aggregation, and cross-repository question tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.models.db import Analysis, Base, QuestionRow, Repo, SkillStatusRow, User
from app.routers import recall as recall_router
from app.schemas.repo_map import FunctionNode, RepoMap
from app.services.portfolio import build_profile, replace_selection


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_portfolio(db: Session, root: Path) -> list[Repo]:
    db.add(User(id=1, github_login="developer", github_token="token"))
    repos: list[Repo] = []
    for index in range(3):
        repo_id = 10 + index
        clone = root / f"repo-{index}"
        clone.mkdir()
        (clone / "app.py").write_text(
            f"def portfolio_function_{index}():\n    return {index}\n", encoding="utf-8"
        )
        repo = Repo(
            id=repo_id,
            user_id=1,
            full_name=f"owner/repo-{index}",
            language="Python",
            clone_path=str(clone),
        )
        repos.append(repo)
        function = FunctionNode(
            name=f"portfolio_function_{index}",
            file="app.py",
            lines=(1, 2),
            complexity=12 + index,
            loc=2,
            last_modified=datetime.now(UTC) - timedelta(days=45),
            author_ratio=1.0,
        )
        repo_map = RepoMap(
            repo=repo.full_name,
            language="python",
            analyzed_at=datetime.now(UTC),
            total_files=index + 1,
            excluded_files=["vendor.py"] if index == 0 else [],
            functions=[function],
        )
        evidence = {"file": "app.py", "lines": [1, 2], "commit": None}
        scores = {
            "repo": repo.full_name,
            "dimensions": [
                {
                    "dimension": "code_structure",
                    "level": index + 1,
                    "rationale": f"Repository {index} evidence.",
                    "evidence": [evidence],
                    "metric_basis": {},
                }
            ],
            "skills": [
                {"skill_id": "python", "tier": "touched", "evidence": [evidence]}
            ],
        }
        db.add(repo)
        db.add(
            Analysis(
                repo_id=repo_id,
                stage="done",
                progress=100,
                repo_map=repo_map.model_dump(mode="json"),
                findings=[
                    {
                        "id": f"finding-{index}",
                        "dimension": "code_structure",
                        "severity": "medium",
                        "observation": f"Finding from repo {index}.",
                        "evidence": evidence,
                        "confidence": 0.9,
                    }
                ],
                scores=scores,
            )
        )
        db.add(
            SkillStatusRow(
                user_id=1,
                repo_id=repo_id,
                skill_id="python",
                tier="verified" if index == 2 else "touched",
                evidence=[evidence],
            )
        )
    db.commit()
    replace_selection(db, "developer", [str(repo.id) for repo in repos])
    return repos


def test_portfolio_profile_aggregates_all_selected_repositories(db: Session, tmp_path: Path):
    _seed_portfolio(db, tmp_path)

    profile = build_profile(db, "developer")

    assert len(profile.repositories) == 3
    assert profile.total_files == 6
    assert profile.total_functions == 3
    assert profile.excluded_files == 1
    assert profile.scores.dimensions[0].level == 2
    assert profile.scores.skills[0].tier.value == "verified"
    assert {item.evidence.repo_id for item in profile.findings} == {"10", "11", "12"}
    assert {item.id for item in profile.findings} == {
        "10:finding-0",
        "11:finding-1",
        "12:finding-2",
    }


def test_selection_rejects_fewer_than_three_repositories(db: Session, tmp_path: Path):
    repos = _seed_portfolio(db, tmp_path)

    with pytest.raises(ValueError, match="between 3 and 5"):
        replace_selection(db, "developer", [str(repos[0].id), str(repos[1].id)])


def test_portfolio_questions_use_combined_summary_and_keep_repo_origins(
    db: Session, tmp_path: Path, monkeypatch
):
    _seed_portfolio(db, tmp_path)
    captured: dict = {}

    def personalize(settings, questions, portfolio_summary):
        captured["calls"] = captured.get("calls", 0) + 1
        captured["summary"] = portfolio_summary
        captured["questions"] = questions
        return questions

    monkeypatch.setattr(
        recall_router, "get_settings", lambda: Settings(mock_mode=False, llm_provider="openai")
    )
    monkeypatch.setattr(recall_router, "personalize_for_portfolio", personalize)

    questions = recall_router.portfolio_questions("developer", db)

    assert len(questions) == 3
    assert {question.target.repo_id for question in questions} == {"10", "11", "12"}
    assert len(captured["summary"]["repositories"]) == 3
    assert len(captured["summary"]["top_findings"]) == 3
    stored = db.scalars(select(QuestionRow)).all()
    assert len(stored) == 3
    assert {row.repo_id for row in stored} == {10, 11, 12}
    cached = recall_router.portfolio_questions("developer", db)
    assert [question.id for question in cached] == [question.id for question in questions]
    assert captured["calls"] == 1
