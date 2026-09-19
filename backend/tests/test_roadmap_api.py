"""Persisted recall promotions flow into the real roadmap endpoint."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.db import Base, QuestionRow, Repo, SkillStatusRow, User
from app.routers import recall as recall_router
from app.routers import roadmap as roadmap_router
from app.schemas.recall import Answer, GradeResult, Question
from app.schemas.scores import Tier


def test_real_roadmap_moves_verified_skill_from_revise_to_deepen(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    evidence = [{"file": "app.py", "lines": [1, 2], "commit": "abc"}]
    with Session(engine) as db:
        db.add(User(id=1, github_login="developer"))
        db.add(Repo(id=10, user_id=1, full_name="owner/project"))
        db.add_all(
            [
                SkillStatusRow(
                    user_id=1,
                    repo_id=10,
                    skill_id="python",
                    tier="verified",
                    evidence=evidence,
                ),
                SkillStatusRow(
                    user_id=1,
                    repo_id=10,
                    skill_id="testing_unit",
                    tier="touched",
                    evidence=evidence,
                ),
            ]
        )
        db.commit()
        monkeypatch.setattr(
            roadmap_router,
            "get_settings",
            lambda: Settings(mock_mode=False, demand_source="seeded"),
        )

        result = roadmap_router.roadmap("10", "developer", db)

        assert [item.skill_id for item in result.deepen] == ["python"]
        assert [item.skill_id for item in result.revise] == ["testing_unit"]
        assert result.deepen[0].evidence[0].file == "app.py"
        assert result.learn_new


def test_real_roadmap_rejects_another_users_repo(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, github_login="developer"))
        db.add(Repo(id=10, user_id=1, full_name="owner/project"))
        db.commit()
        monkeypatch.setattr(
            roadmap_router,
            "get_settings",
            lambda: Settings(mock_mode=False, demand_source="seeded"),
        )

        try:
            roadmap_router.roadmap("10", "intruder", db)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404
        else:
            raise AssertionError("another user must not read this roadmap")


def test_passing_transfer_answer_immediately_changes_roadmap_bucket(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    question = Question.model_validate(
        {
            "id": "q-transfer",
            "type": "transfer",
            "target": {"file": "app.py", "lines": [1, 2], "commit": "abc"},
            "target_name": "run",
            "prompt": "How would this transfer?",
            "code_context": "def run(): pass",
            "skill_ids": ["python"],
        }
    )
    settings = Settings(mock_mode=False, demand_source="seeded")
    monkeypatch.setattr(roadmap_router, "get_settings", lambda: settings)
    monkeypatch.setattr(recall_router, "get_settings", lambda: settings)
    monkeypatch.setattr(
        recall_router,
        "grade",
        lambda *args, **kwargs: GradeResult(
            question_id=question.id,
            passed=True,
            score=0.9,
            feedback="Transfer reasoning is grounded.",
            tier_change={"python": Tier.VERIFIED},
        ),
    )
    with Session(engine) as db:
        db.add(User(id=1, github_login="developer"))
        db.add(Repo(id=10, user_id=1, full_name="owner/project", clone_path=str(tmp_path)))
        db.add(
            SkillStatusRow(
                user_id=1,
                repo_id=10,
                skill_id="python",
                tier="touched",
                evidence=[],
            )
        )
        db.add(
            QuestionRow(
                id=question.id,
                repo_id=10,
                type="transfer",
                payload=question.model_dump(mode="json"),
            )
        )
        db.commit()
        assert [item.skill_id for item in roadmap_router.roadmap("10", "developer", db).revise] == ["python"]

        recall_router.submit_answer(
            Answer(question_id=question.id, submission="A grounded answer."), "developer", db
        )
        updated = roadmap_router.roadmap("10", "developer", db)

        assert updated.revise == []
        assert [item.skill_id for item in updated.deepen] == ["python"]
