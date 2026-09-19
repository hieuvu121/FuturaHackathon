"""Phase 3 exit path: analysis artifacts -> five answers -> roadmap promotion."""

from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.db import AnswerRow, Base, QuestionRow, Repo, User
from app.routers import analysis as analysis_router
from app.routers import recall as recall_router
from app.routers import repos as repos_router
from app.routers import roadmap as roadmap_router
from app.schemas.findings import Finding
from app.schemas.recall import GENERATED_TYPES, Answer, GradeResult, Question, QuestionType
from app.schemas.repo_map import FunctionNode, RepoMap
from app.schemas.scores import Scores, SkillStatus, Tier
from app.services.analyze import AnalysisArtifacts
from app.services.storage import complete_analysis, start_analysis


def test_five_answer_flow_promotes_verified_skills_into_deepen(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = Settings(mock_mode=False, demand_source="seeded")
    for module in (analysis_router, recall_router, repos_router, roadmap_router):
        monkeypatch.setattr(module, "get_settings", lambda: settings)

    source = tmp_path / "app.py"
    source.write_text("def run():\n    return True\n", encoding="utf-8")
    evidence = {"file": "app.py", "lines": [1, 2], "commit": "abc"}
    repo_map = RepoMap(
        repo="owner/project",
        language="python",
        analyzed_at=datetime.now(UTC),
        total_files=1,
        functions=[
            FunctionNode(name="run", file="app.py", lines=(1, 2), complexity=1, loc=2)
        ],
    )
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
    skill_ids = ["python", "testing_unit", "git", "clean_code", "debugging"]
    artifacts = AnalysisArtifacts(
        repo_map=repo_map,
        findings=[finding],
        dropped_findings=[],
        scores=Scores(
            repo="owner/project",
            skills=[
                SkillStatus.model_validate(
                    {"skill_id": skill_id, "tier": "touched", "evidence": [evidence]}
                )
                for skill_id in skill_ids
            ],
        ),
        repository_metrics={},
    )

    with Session(engine) as db:
        db.add(User(id=1, github_login="developer"))
        repo = Repo(
            id=10,
            user_id=1,
            full_name="owner/project",
            language="Python",
            clone_path=str(tmp_path),
        )
        db.add(repo)
        db.commit()
        complete_analysis(db, start_analysis(db, repo), repo, artifacts)

        questions = []
        for index, question_type in enumerate(GENERATED_TYPES):
            question = Question.model_validate(
                {
                    "id": f"q-{index}",
                    "type": question_type,
                    "target": evidence,
                    "target_name": "run",
                    "prompt": f"{question_type.value} prompt",
                    "code_context": source.read_text(encoding="utf-8"),
                    "skill_ids": [skill_ids[index]],
                }
            )
            questions.append(question)
            db.add(
                QuestionRow(
                    id=question.id,
                    repo_id=repo.id,
                    type=question.type.value,
                    payload=question.model_dump(mode="json"),
                )
            )
        db.commit()

        assert repos_router.status("10", "developer", db)["stage"] == "done"
        assert repos_router.repo_map("10", "developer", db)["repo"] == "owner/project"
        assert analysis_router.scores("10", "developer", db).repo == "owner/project"
        assert [item.id for item in analysis_router.findings("10", "developer", db)] == [
            "grounded"
        ]
        before = roadmap_router.roadmap("10", "developer", db)
        assert {item.skill_id for item in before.revise} == set(skill_ids)

        def fake_grade(settings, question, answer, **kwargs):
            promotes = question.type in {
                QuestionType.TRANSFER,
                QuestionType.DEBUG,
                QuestionType.EXTEND,
            }
            return GradeResult(
                question_id=question.id,
                passed=True,
                score=0.9,
                feedback="Evidence-backed revision feedback.",
                tier_change={question.skill_ids[0]: Tier.VERIFIED} if promotes else {},
            )

        monkeypatch.setattr(recall_router, "grade", fake_grade)
        results = [
            recall_router.submit_answer(
                Answer(question_id=question.id, submission="A grounded response."),
                "developer",
                db,
            )
            for question in questions
        ]

        assert len(results) == 5
        assert len(db.scalars(select(AnswerRow)).all()) == 5
        after = roadmap_router.roadmap("10", "developer", db)
        assert {item.skill_id for item in after.deepen} == {
            "git",
            "clean_code",
            "debugging",
        }
        assert {item.skill_id for item in after.revise} == {"python", "testing_unit"}
