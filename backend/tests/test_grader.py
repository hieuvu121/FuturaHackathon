from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.db import AnswerRow, Base, QuestionRow, Repo, SkillStatusRow, User
from app.routers import recall as recall_router
from app.schemas.recall import Answer, Question
from app.schemas.recall import GradeResult
from app.schemas.scores import Tier
from app.services.recall import grader


def _question(kind: str = "transfer") -> Question:
    return Question.model_validate(
        {
            "id": "q-1",
            "type": kind,
            "target": {"file": "maths.py", "lines": [1, 2]},
            "target_name": "add",
            "prompt": "Explain the change.",
            "code_context": "def add(left, right): return left + right",
            "skill_ids": ["python"],
        }
    )


def test_transfer_success_promotes_skills(monkeypatch):
    monkeypatch.setattr(
        grader,
        "_grade_open",
        lambda *args: grader.RubricResult(score=0.8, feedback="Good revision reasoning."),
    )
    result = grader.grade(Settings(), _question(), Answer(question_id="q-1", submission="Because..."))
    assert result.passed is True
    assert result.tier_change["python"].value == "verified"


def test_recall_success_does_not_promote(monkeypatch):
    monkeypatch.setattr(
        grader,
        "_grade_open",
        lambda *args: grader.RubricResult(score=0.9, feedback="Accurate recall."),
    )
    result = grader.grade(
        Settings(), _question("recall"), Answer(question_id="q-1", submission="It adds values.")
    )
    assert result.passed is True
    assert result.tier_change == {}


def test_debug_submission_is_verified_by_real_tests(tmp_path: Path):
    (tmp_path / "maths.py").write_text(
        "def add(left, right):\n    return left - right\n", encoding="utf-8"
    )
    (tmp_path / "test_maths.py").write_text(
        "from maths import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8"
    )
    answer = Answer(
        question_id="q-1",
        submission="def add(left, right):\n    return left + right",
    )
    result = grader.grade(Settings(), _question("debug"), answer, root=tmp_path)
    assert result.passed is True
    assert result.score == 1.0


def test_answer_endpoint_persists_result_and_promotes_skill(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    question = _question()
    with Session(engine) as db:
        db.add(User(id=1, github_login="developer"))
        db.add(Repo(id=10, user_id=1, full_name="owner/project", clone_path=str(tmp_path)))
        db.add(
            QuestionRow(
                id=question.id,
                repo_id=10,
                type=question.type.value,
                payload=question.model_dump(mode="json"),
            )
        )
        db.add(
            SkillStatusRow(
                user_id=1,
                repo_id=10,
                skill_id="python",
                tier="touched",
                evidence=[],
            )
        )
        db.commit()
        monkeypatch.setattr(recall_router, "get_settings", lambda: Settings(mock_mode=False))
        monkeypatch.setattr(
            recall_router,
            "grade",
            lambda *args, **kwargs: GradeResult(
                question_id="q-1",
                passed=True,
                score=0.8,
                feedback="Good transfer reasoning.",
                tier_change={"python": Tier.VERIFIED},
            ),
        )

        result = recall_router.submit_answer(
            Answer(question_id="q-1", submission="A reasoned response."), "developer", db
        )

        stored_answer = db.scalar(select(AnswerRow))
        skill = db.scalar(select(SkillStatusRow))
        assert result.passed is True
        assert stored_answer.score == 0.8
        assert skill.tier == "verified"
        assert skill.evidence[0]["file"] == "maths.py"
