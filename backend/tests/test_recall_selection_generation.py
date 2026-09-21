"""Recall target selection and deterministic question generation tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import Settings
from app.models.db import Analysis, Base, QuestionRow, Repo, User
from app.routers import recall as recall_router
from app.schemas.findings import Finding
from app.schemas.repo_map import FunctionNode, RepoMap
from app.schemas.recall import GENERATED_TYPES, QuestionType
from app.services.recall.generator import MAX_CONTEXT_CHARS, build_context, generate
from app.services.recall.selector import select_targets
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


NOW = datetime(2026, 9, 20, tzinfo=UTC)


def _function(name: str, *, days: int = 60, complexity: int = 10, **kwargs) -> FunctionNode:
    return FunctionNode(
        name=name,
        file=f"{name}.py",
        lines=(1, 2),
        complexity=complexity,
        loc=2,
        last_modified=NOW - timedelta(days=days),
        **kwargs,
    )


def _repo(functions) -> RepoMap:
    return RepoMap(
        repo="owner/project",
        language="python",
        analyzed_at=NOW,
        total_files=len(functions),
        functions=functions,
    )


def test_selector_enforces_all_conditions_and_prefers_high_findings():
    preferred = _function("preferred", complexity=10, author_ratio=0.8)
    complex_target = _function("complex", complexity=20, author_ratio=0.8)
    rejected = [
        _function("recent", days=10),
        _function("old", days=100),
        _function("simple", complexity=9),
        _function("tested", has_test=True),
        _function("foreign", author_ratio=0.5),
    ]
    finding = Finding.model_validate(
        {
            "id": "high",
            "dimension": "code_structure",
            "severity": "high",
            "observation": "Grounded.",
            "evidence": {"file": preferred.file, "lines": preferred.lines},
            "confidence": 0.9,
        }
    )

    selected = select_targets(_repo([complex_target, preferred, *rejected]), [finding], now=NOW)

    assert [item.name for item in selected] == ["preferred", "complex"]


def test_context_contains_target_callee_and_commit_diff(tmp_path: Path):
    target = _function("target", calls=["helper"], created_commit="abc")
    helper = _function("helper")
    (tmp_path / "target.py").write_text("def target():\n    helper()\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("def helper():\n    return 1\n", encoding="utf-8")

    context = build_context(tmp_path, _repo([target, helper]), target)

    assert "# Target: target.py::target" in context
    assert "# Callee: helper.py::helper" in context
    assert len(context) <= MAX_CONTEXT_CHARS


def test_generator_emits_five_stable_typed_questions(tmp_path: Path):
    targets = [_function(f"function_{index}") for index in range(5)]
    for target in targets:
        (tmp_path / target.file).write_text(
            f"def {target.name}():\n    return {target.name!r}\n", encoding="utf-8"
        )
    settings = Settings()

    first = generate(settings, tmp_path, _repo(targets), targets)
    second = generate(settings, tmp_path, _repo(targets), targets)

    assert [item.type for item in first] == list(GENERATED_TYPES)
    assert [item.id for item in first] == [item.id for item in second]
    assert all(item.skill_ids[0] == "python" for item in first)
    assert "testing_unit" in first[-1].skill_ids


def test_real_questions_endpoint_generates_and_persists(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    target = _function("eligible", complexity=12, author_ratio=1.0)
    (tmp_path / target.file).write_text("def eligible():\n    return True\n", encoding="utf-8")
    with Session(engine) as db:
        db.add(User(id=1, github_login="developer"))
        db.add(
            Repo(
                id=10,
                user_id=1,
                full_name="owner/project",
                language="Python",
                clone_path=str(tmp_path),
            )
        )
        db.add(
            Analysis(
                id=1,
                repo_id=10,
                stage="done",
                progress=100,
                repo_map=_repo([target]).model_dump(mode="json"),
                findings=[],
            )
        )
        db.commit()
        monkeypatch.setattr(recall_router, "get_settings", lambda: Settings(mock_mode=False))

        result = recall_router.questions("10", "developer", db)

        assert len(result) == 1
        stored = db.scalar(select(QuestionRow).where(QuestionRow.repo_id == 10))
        assert stored.payload["id"] == result[0].id
