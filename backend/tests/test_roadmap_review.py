"""Five recall questions, then a roadmap the user can accept, retest, or edit."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.db import Base, RecallAttemptRow, User
from app.routers import drills as drills_router
from app.routers import roadmap as roadmap_router
from app.routers import roadmap_review as review_router
from app.schemas.recall import Answer
from app.schemas.roadmap import Bucket, Buckets, NodeStatus, ReviewStatus, RoadmapItem, TailorRequest
from app.services.knowledge import get_taxonomy
from app.services.roadmap import review
from app.services.roadmap.concepts import graph_from_buckets, tailor

MOCK = Settings(mock_mode=True, openai_api_key="", anthropic_api_key="")
LOGIN = "demo-user"


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    for module in (drills_router, roadmap_router, review_router):
        monkeypatch.setattr(module, "get_settings", lambda: MOCK)
    with Session(engine) as session:
        yield session


def _answer_current(db, right: bool = True):
    step = drills_router.next_drill(LOGIN, db)
    question = step.question
    entry = drills_router.entry_for(MOCK, question.id)
    if question.choices:
        pick = entry.answer if right else next(c for c in question.choices if c != entry.answer)
    else:
        pick = " ".join(entry.key_points) if right else "no idea"
    return drills_router.answer_drill(Answer(question_id=question.id, submission=pick), LOGIN, db)


def test_a_session_is_five_questions_and_then_it_ends(db):
    first = drills_router.next_drill(LOGIN, db)
    assert first.question is not None
    assert first.session_length == 5

    grades = [_answer_current(db, right=index % 2 == 0) for index in range(5)]

    assert [grade.next.question is not None for grade in grades] == [True, True, True, True, False]
    assert grades[-1].next.asked == 5
    finished = drills_router.next_drill(LOGIN, db)
    assert finished.question is None
    assert finished.asked == 5


def test_a_finished_session_refuses_a_sixth_answer(db):
    step = drills_router.next_drill(LOGIN, db)
    for _ in range(5):
        _answer_current(db)

    with pytest.raises(Exception) as caught:
        drills_router.answer_drill(Answer(question_id=step.question.id, submission="x"), LOGIN, db)
    assert getattr(caught.value, "status_code", None) == 409


def test_finishing_recall_puts_an_accepted_roadmap_back_up_for_agreement(db):
    drills_router.next_drill(LOGIN, db)
    assert review_router.accept(LOGIN, db).status is ReviewStatus.ACCEPTED

    for _ in range(5):
        _answer_current(db)

    state = review_router.current(LOGIN, db)
    assert state.status is ReviewStatus.PENDING
    assert state.recall_answered == 5


def test_disputing_by_retest_starts_a_fresh_session_without_deleting_answers(db):
    drills_router.next_drill(LOGIN, db)
    for _ in range(5):
        _answer_current(db, right=False)
    before = drills_router.next_drill(LOGIN, db)
    assert before.question is None

    state = review_router.redo(LOGIN, db)

    assert state.recall_answered == 0
    assert state.status is ReviewStatus.PENDING
    again = drills_router.next_drill(LOGIN, db)
    assert again.question is not None
    assert again.asked == 0
    assert db.query(RecallAttemptRow).count() == 5
    # The old answers no longer move the roadmap either.
    owner = db.query(User).filter_by(github_login=LOGIN).one()
    assert review.recall_levels(db, owner.id) == {}


def test_this_sessions_answers_are_what_the_roadmap_is_drawn_from(db):
    first = drills_router.next_drill(LOGIN, db)
    skill_id, level = first.question.skill_ids[0], first.question.level
    _answer_current(db, right=False)
    owner = db.query(User).filter_by(github_login=LOGIN).one()

    assert review.recall_levels(db, owner.id) == {skill_id: (set(), {level})}


def _graph():
    def item(skill_id, name, bucket):
        return RoadmapItem(skill_id=skill_id, skill_name=name, bucket=bucket, reason="", priority=0.5)

    buckets = Buckets(
        role="software_engineer",
        region="AU",
        deepen=[item("python", "Python", Bucket.DEEPEN)],
        revise=[item("git", "Git", Bucket.REVISE)],
        learn_new=[item("go", "Go", Bucket.LEARN_NEW), item("docker", "Docker", Bucket.LEARN_NEW)],
    )
    return graph_from_buckets(buckets, get_taxonomy(MOCK))


def test_tailoring_removes_skills_and_recounts_what_is_left():
    graph = tailor(_graph(), {"go", "docker"})

    skills = {s.skill_id for c in graph.concepts for s in c.skills}
    assert skills == {"python", "git"}
    # Docker was the only DevOps skill, so its concept goes with it.
    assert "devops" not in {c.concept_id for c in graph.concepts}
    languages = next(c for c in graph.concepts if c.concept_id == "programming_languages")
    assert languages.new_count == 0
    assert languages.mastery == 1.0


def test_the_tailoring_view_gets_hidden_skills_back_flagged():
    graph = tailor(_graph(), {"go", "docker"}, keep_hidden=True)

    flags = {s.skill_id: s.hidden for c in graph.concepts for s in c.skills}
    assert flags == {"python": False, "git": False, "go": True, "docker": True}
    devops = next(c for c in graph.concepts if c.concept_id == "devops")
    assert devops.mastery == 0.0 and devops.new_count == 0
    assert all(s.status is NodeStatus.NEW for s in devops.skills)


def test_disputing_by_tailoring_is_stored_applied_and_then_accepted(db):
    full = roadmap_router.portfolio_roadmap_graph(LOGIN, db)
    drills_router.next_drill(LOGIN, db)  # creates the demo user
    victim = full.concepts[0].skills[0].skill_id

    state = review_router.tailor(TailorRequest(hidden_skills=[victim, victim, " "]), LOGIN, db)

    assert state.hidden_skills == [victim]
    assert state.status is ReviewStatus.PENDING
    served = roadmap_router.portfolio_roadmap_graph(LOGIN, db)
    assert victim not in {s.skill_id for c in served.concepts for s in c.skills}
    editing = roadmap_router.portfolio_roadmap_graph(LOGIN, db, include_hidden=True)
    assert [s.skill_id for c in editing.concepts for s in c.skills if s.hidden] == [victim]

    assert review_router.accept(LOGIN, db).status is ReviewStatus.ACCEPTED
    assert review_router.tailor(TailorRequest(hidden_skills=[]), LOGIN, db).status is ReviewStatus.PENDING



def test_a_session_mixes_coding_tasks_with_multiple_choice(db):
    kinds: list[str] = []
    choices: list[int] = []
    for _ in range(5):
        question = drills_router.next_drill(LOGIN, db).question
        kinds.append(question.type.value)
        choices.append(len(question.choices))
        _answer_current(db, right=True)

    assert kinds[0] == "coding"
    # All three kinds turn up in one session: write it, pick it, explain it.
    assert set(kinds) == {"coding", "concept", "explain"}
    assert kinds.count("concept") >= 2
    # Theory is always multiple choice; coding and explain answers are always written.
    assert all((count == 4) == (kind == "concept") for kind, count in zip(kinds, choices))
