"""Coding drills grounded in the user's own repository, and what they do to the roadmap."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.db import Base, QuestionRow, Repo
from app.schemas.common import Evidence
from app.schemas.recall import QuestionType
from app.schemas.roadmap import NodeStatus
from app.schemas.scores import SkillStatus, Tier
from app.services.recall import repo_drills
from app.services.recall.adaptive import Attempt, next_question
from app.services.recall.drills import _prompt
from app.services.recall.repo_drills import (
    DrillTaskBatch,
    ensure_repo_drills,
    load_repo_entries,
    repo_entry_for,
    snippet_for,
)
from app.services.roadmap.concepts import recall_mastery

SETTINGS = Settings(mock_mode=False, llm_provider="openai", openai_api_key="test-key")
SOURCE = "\n".join(
    [
        "def dedupe(rows):",
        "    seen = set()",
        "    kept = []",
        "    for row in rows:",
        "        if row.id not in seen:",
        "            seen.add(row.id)",
        "            kept.append(row)",
        "    return kept",
    ]
)


def _tasks(*levels: int) -> DrillTaskBatch:
    return DrillTaskBatch.model_validate(
        {
            "tasks": [
                {
                    "level": level,
                    "prompt": f"In dedupe(), handle rows without an id (level {level}).",
                    "starter": "def dedupe(rows):\n    ",
                    "key_points": ["skips missing id", "keeps order", "single pass"],
                    "solution": "def dedupe(rows): ...",
                }
                for level in levels
            ]
        }
    )


def _db(tmp_path, monkeypatch):
    repo_drills._failed_at.clear()
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "app.py").write_text(SOURCE + "\n", encoding="utf-8")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    repo = Repo(id=10, user_id=1, full_name="dev/project", language="Python", clone_path=str(clone))
    db.add(repo)
    db.commit()
    skills = [
        SkillStatus(
            skill_id="python",
            tier=Tier.TOUCHED,
            evidence=[Evidence(file="app.py", lines=(1, 8), commit="abc", repo_id="10")],
        )
    ]
    return db, repo, skills


def _stub(monkeypatch, batch: DrillTaskBatch) -> list[str]:
    prompts: list[str] = []

    def fake(settings, prompt):
        prompts.append(prompt)
        return batch

    monkeypatch.setattr(repo_drills, "_request_tasks", fake)
    return prompts


def test_drills_are_written_about_the_users_own_code(tmp_path, monkeypatch):
    db, repo, skills = _db(tmp_path, monkeypatch)
    prompts = _stub(monkeypatch, _tasks(2, 3))

    entries = ensure_repo_drills(db, SETTINGS, "dev", skills, [repo], [("python", "Python")])

    assert [entry.question.level for entry in entries] == [2, 3]
    question = entries[0].question
    assert question.type is QuestionType.CODING
    assert question.skill_ids == ["python"]
    assert question.code_context == SOURCE
    assert question.target.file == "app.py"
    assert question.target.repo_id == "10"
    assert "dev/project" in question.target_name
    assert entries[0].key_points == ["skips missing id", "keeps order", "single pass"]
    assert SOURCE in prompts[0]
    assert "Python" in prompts[0]


def test_generation_happens_once_and_is_read_back_from_storage(tmp_path, monkeypatch):
    db, repo, skills = _db(tmp_path, monkeypatch)
    prompts = _stub(monkeypatch, _tasks(2, 3))
    first = ensure_repo_drills(db, SETTINGS, "dev", skills, [repo], [("python", "Python")])

    second = ensure_repo_drills(db, SETTINGS, "dev", skills, [repo], [("python", "Python")])

    assert len(prompts) == 1
    assert second == first
    assert load_repo_entries(db, [10]) == first
    assert len(db.scalars(select(QuestionRow)).all()) == 2


def test_repository_drill_replaces_the_seeded_question_at_its_level(tmp_path, monkeypatch):
    db, repo, skills = _db(tmp_path, monkeypatch)
    _stub(monkeypatch, _tasks(2, 3))
    entries = ensure_repo_drills(db, SETTINGS, "dev", skills, [repo], [("python", "Python")])
    order = [("python", "Python")]

    seeded = next_question(SETTINGS, [], order)
    grounded = next_question(SETTINGS, [], order, entries)
    harder = next_question(
        SETTINGS, [Attempt("python", 2, True, grounded.question.id)], order, entries
    )
    easier = next_question(
        SETTINGS, [Attempt("python", 2, False, grounded.question.id)], order, entries
    )

    # A seeded drill may show code (an explain drill does), but never the user's own.
    assert seeded.question.target is None
    assert grounded.question.id == entries[0].question.id
    assert harder.question.id == entries[1].question.id
    # Level 1 has no repository drill, so the loop falls back to the seeded bank.
    assert easier.question.level == 1
    assert easier.question.target is None


def test_malformed_tasks_are_dropped(tmp_path, monkeypatch):
    db, repo, skills = _db(tmp_path, monkeypatch)
    batch = _tasks(2, 2, 4)
    batch.tasks.append(batch.tasks[0].model_copy(update={"level": 3, "key_points": [" "]}))
    _stub(monkeypatch, batch)

    entries = ensure_repo_drills(db, SETTINGS, "dev", skills, [repo], [("python", "Python")])

    assert [entry.question.level for entry in entries] == [2]


def test_provider_failure_falls_back_to_the_bank_and_is_not_retried_at_once(tmp_path, monkeypatch):
    db, repo, skills = _db(tmp_path, monkeypatch)
    calls: list[str] = []

    def fail(settings, prompt):
        calls.append(prompt)
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(repo_drills, "_request_tasks", fail)

    assert ensure_repo_drills(db, SETTINGS, "dev", skills, [repo], [("python", "Python")]) == ()
    assert ensure_repo_drills(db, SETTINGS, "dev", skills, [repo], [("python", "Python")]) == ()
    assert len(calls) == 1
    assert next_question(SETTINGS, [], [("python", "Python")], ()).question is not None


def test_missing_credentials_never_raise(tmp_path, monkeypatch):
    db, repo, skills = _db(tmp_path, monkeypatch)
    settings = SETTINGS.model_copy(update={"openai_api_key": ""})

    assert ensure_repo_drills(db, settings, "dev", skills, [repo], [("python", "Python")]) == ()


def test_evidence_outside_the_clone_or_too_short_is_not_used(tmp_path, monkeypatch):
    db, repo, _ = _db(tmp_path, monkeypatch)
    (tmp_path / "secret.py").write_text(SOURCE, encoding="utf-8")
    skill = SkillStatus(
        skill_id="python",
        tier=Tier.TOUCHED,
        evidence=[
            Evidence(file="../secret.py", lines=(1, 8), repo_id="10"),
            Evidence(file="app.py", lines=(9, 12), repo_id="10"),
            Evidence(file="app.py", lines=(1, 8), repo_id="99"),
            Evidence(file="missing.py", lines=(1, 8), repo_id="10"),
        ],
    )

    assert snippet_for(skill, {10: repo}) is None


def test_a_short_citation_is_widened_to_the_code_around_it(tmp_path, monkeypatch):
    db, repo, _ = _db(tmp_path, monkeypatch)
    skill = SkillStatus(
        skill_id="python",
        tier=Tier.TOUCHED,
        evidence=[Evidence(file="app.py", lines=(5, 6), repo_id="10")],
    )

    snippet = snippet_for(skill, {10: repo})

    assert snippet.code == SOURCE
    assert snippet.evidence.lines == (1, 8)


def test_a_drill_is_only_gradable_by_the_owner_of_its_repository(tmp_path, monkeypatch):
    db, repo, skills = _db(tmp_path, monkeypatch)
    _stub(monkeypatch, _tasks(2))
    entry = ensure_repo_drills(db, SETTINGS, "dev", skills, [repo], [("python", "Python")])[0]

    assert repo_entry_for(db, [10], entry.question.id) == entry
    assert repo_entry_for(db, [11], entry.question.id) is None
    assert repo_entry_for(db, [10], "python_l2_dedupe") is None


def test_the_grader_is_shown_the_code_the_task_is_about(tmp_path, monkeypatch):
    db, repo, skills = _db(tmp_path, monkeypatch)
    _stub(monkeypatch, _tasks(2))
    entry = ensure_repo_drills(db, SETTINGS, "dev", skills, [repo], [("python", "Python")])[0]

    assert "seen.add(row.id)" in _prompt(entry, "def dedupe(rows): ...")


def test_recall_results_replace_the_status_guess_for_mastery():
    untested = (set(), set())
    assert recall_mastery(NodeStatus.FAMILIAR, *untested) == 0.5
    assert recall_mastery(NodeStatus.VERIFIED, *untested) == 1.0
    assert recall_mastery(NodeStatus.NEW, *untested) == 0.0

    assert recall_mastery(NodeStatus.FAMILIAR, {1}, {2}) == 0.25
    assert recall_mastery(NodeStatus.FAMILIAR, {2}, {3}) == 0.5
    assert recall_mastery(NodeStatus.FAMILIAR, set(), {1, 2}) == 0.1
    assert recall_mastery(NodeStatus.NEW, set(), {2}) == 0.0
    assert recall_mastery(NodeStatus.NEW, {2}, set()) == 0.5
    assert recall_mastery(NodeStatus.VERIFIED, {3}, {4}) == 0.75
    assert recall_mastery(NodeStatus.VERIFIED, {3, 4}, set()) == 1.0


def test_a_persons_level_is_read_off_the_bar():
    from app.schemas.roadmap import Proficiency
    from app.services.roadmap.concepts import proficiency_of

    cases = {
        # untested
        (NodeStatus.NEW, (), ()): Proficiency.BEGINNER,
        (NodeStatus.FAMILIAR, (), ()): Proficiency.INTERMEDIATE,
        # tested: only "can name it", or nothing at all
        (NodeStatus.FAMILIAR, (1,), (2,)): Proficiency.BEGINNER,
        (NodeStatus.FAMILIAR, (), (1, 2)): Proficiency.BEGINNER,
        # tested: can explain it, can reason about it
        (NodeStatus.NEW, (2,), (3,)): Proficiency.INTERMEDIATE,
        (NodeStatus.VERIFIED, (3,), (4,)): Proficiency.INTERMEDIATE,
        # tested: cleared the hardest level
        (NodeStatus.VERIFIED, (3, 4), ()): Proficiency.EXPERT,
    }
    for (status, passed, failed), expected in cases.items():
        assert proficiency_of(recall_mastery(status, set(passed), set(failed))) is expected, (status, passed, failed)

