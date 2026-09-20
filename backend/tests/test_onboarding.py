"""The first step: no repositories, so a survey -- and a roadmap that stays honest about it."""

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.db import Base, LearnerProfileRow, User
from app.routers import drills as drills_router
from app.routers import onboarding as onboarding_router
from app.routers import roadmap as roadmap_router
from app.routers import roadmap_review as review_router
from app.routers.onboarding import SurveyAnswers
from app.schemas.recall import Answer
from app.schemas.roadmap import NodeStatus, ReviewStatus
from app.services.knowledge import get_taxonomy
from app.services.recall.adaptive import load_bank
from app.services.roadmap import survey

LIVE = Settings(mock_mode=False, openai_api_key="", anthropic_api_key="")


class FakeRequest:
    """Just enough of a Starlette request: the signed-cookie session is a dict."""

    def __init__(self, user: str | None = None):
        self.session: dict = {"user": user} if user else {}


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    for module in (onboarding_router, roadmap_router, drills_router, review_router):
        monkeypatch.setattr(module, "get_settings", lambda: LIVE)
    with Session(engine) as session:
        yield session


def _skills(graph):
    return {s.skill_id: s for c in graph.concepts for s in c.skills}


def test_every_role_path_uses_real_skills_and_has_questions_to_ask():
    taxonomy = get_taxonomy(LIVE)
    raw = yaml.safe_load((LIVE.knowledge_data_dir / "role_paths.yaml").read_text(encoding="utf-8"))
    drilled = {entry.question.skill_ids[0] for entry in load_bank(LIVE)}

    assert len(raw["roles"]) >= 5
    for role in raw["roles"]:
        for skill_id in role["skills"]:
            assert taxonomy.normalise(skill_id) == skill_id, (role["id"], skill_id)
        assert len(set(role["skills"])) == len(role["skills"]), role["id"]
        # A recall session needs something to ask: every path must overlap the drill bank.
        assert len(drilled & set(role["skills"])) >= 3, role["id"]

    listed = onboarding_router.roles()
    assert [path.id for path in listed] == [role["id"] for role in raw["roles"]]
    assert all(skill.name for path in listed for skill in path.skills)


def test_a_visitor_who_has_not_chosen_has_no_path_and_is_not_refused(db):
    profile = onboarding_router.profile(FakeRequest(), db)

    assert profile.path is None and profile.user is None and not profile.guest


def test_the_survey_needs_no_login_and_signs_a_guest_in(db):
    request = FakeRequest()

    profile = onboarding_router.submit_survey(
        SurveyAnswers(role="backend", known_skills=["python", "git", "react", "made_up"]), request, db
    )

    assert profile.path == "survey" and profile.role == "backend"
    assert profile.role_name == "Backend engineer"
    assert profile.guest and request.session["user"] == profile.user
    assert profile.user.startswith("guest-")
    # Only skills on the chosen path count: `react` is not a backend skill here, and
    # `made_up` is not a skill at all.
    assert profile.known_skills == ["git", "python"]
    assert db.query(User).filter_by(github_login=profile.user).count() == 1
    assert onboarding_router.profile(request, db).role == "backend"


def test_an_unknown_role_is_refused(db):
    with pytest.raises(Exception) as caught:
        onboarding_router.submit_survey(SurveyAnswers(role="astronaut"), FakeRequest(), db)
    assert getattr(caught.value, "status_code", None) == 422


def test_a_signed_in_user_keeps_their_account_and_can_change_their_answers(db):
    request = FakeRequest("ana")

    onboarding_router.submit_survey(SurveyAnswers(role="frontend", known_skills=["css"]), request, db)
    again = onboarding_router.submit_survey(SurveyAnswers(role="data", known_skills=["sql"]), request, db)

    assert again.user == "ana" and not again.guest
    assert (again.role, again.known_skills) == ("data", ["sql"])
    assert db.query(LearnerProfileRow).count() == 1


def test_the_survey_roadmap_never_calls_a_claim_verified(db):
    request = FakeRequest()
    profile = onboarding_router.submit_survey(
        SurveyAnswers(role="backend", known_skills=["python", "git"]), request, db
    )

    graph = roadmap_router.portfolio_roadmap_graph(profile.user, db)

    assert graph.source == "survey" and graph.role == "backend"
    assert graph.role_name == "Backend engineer"
    skills = _skills(graph)
    assert set(skills) == {s.skill_id for s in survey.role_path(LIVE, get_taxonomy(LIVE), "backend").skills}
    assert skills["python"].status is NodeStatus.FAMILIAR and skills["python"].mastery == 0.5
    assert skills["docker"].status is NodeStatus.NEW and skills["docker"].mastery == 0.0
    assert not any(skill.status is NodeStatus.VERIFIED for skill in skills.values())
    # The wording must not talk about code that does not exist.
    assert "You said you have used Python" in skills["python"].missing
    assert "path to this role" in skills["docker"].missing
    assert not any("repositor" in skill.missing or "Your code" in skill.missing for skill in skills.values())
    assert all(skill.evidence == [] and skill.gap_evidence is None for skill in skills.values())
    assert all(skill.resources for skill in skills.values())
    assert [stage.title for stage in graph.stages][0] == "Learn first"


def test_without_code_or_a_survey_there_is_still_no_roadmap(db):
    db.add(User(github_login="nobody"))
    db.commit()

    with pytest.raises(Exception) as caught:
        roadmap_router.portfolio_roadmap_graph("nobody", db)
    assert getattr(caught.value, "status_code", None) == 404


def test_recall_asks_about_what_they_claimed_first_and_then_moves_the_roadmap(db):
    request = FakeRequest()
    profile = onboarding_router.submit_survey(
        SurveyAnswers(role="backend", known_skills=["sql"]), request, db
    )
    login = profile.user

    asked: list[str] = []
    for _ in range(5):
        question = drills_router.next_drill(login, db).question
        asked.append(question.skill_ids[0])
        entry = drills_router.entry_for(LIVE, question.id)
        # Get the claimed skill wrong, everything else right.
        if question.choices:
            right = question.skill_ids[0] != "sql"
            pick = entry.answer if right else next(c for c in question.choices if c != entry.answer)
        else:
            pick = " ".join(entry.key_points) if question.skill_ids[0] != "sql" else "no idea"
        drills_router.answer_drill(Answer(question_id=question.id, submission=pick), login, db)

    assert "sql" in asked, asked
    assert drills_router.next_drill(login, db).question is None
    assert review_router.current(login, db).status is ReviewStatus.PENDING

    skills = _skills(roadmap_router.portfolio_roadmap_graph(login, db))
    # They said they knew SQL and recall found otherwise: the bar drops below the 50% claim.
    assert skills["sql"].mastery < 0.5
    assert "In recall" in skills["sql"].missing
    # Anything they got right is no longer at zero.
    assert any(s.mastery > 0 for sid, s in skills.items() if sid != "sql" and sid in asked)


def test_the_survey_also_works_in_mock_mode(db, monkeypatch):
    mock = Settings(mock_mode=True, openai_api_key="", anthropic_api_key="")
    for module in (onboarding_router, roadmap_router, drills_router, review_router):
        monkeypatch.setattr(module, "get_settings", lambda: mock)

    before = roadmap_router.portfolio_roadmap_graph("demo-user", db)
    profile = onboarding_router.submit_survey(SurveyAnswers(role="frontend"), FakeRequest(), db)
    after = roadmap_router.portfolio_roadmap_graph("demo-user", db)

    assert profile.user == "demo-user" and not profile.guest
    assert before.source == "repos" and after.source == "survey"
    assert "react" in _skills(after)
    assert drills_router.next_drill("demo-user", db).question is not None


def test_the_profile_says_whether_github_is_really_connected(db):
    db.add(User(github_login="ana", github_token="live-token"))
    db.add(User(github_login="bo", github_token=None))  # signed in once, token since rejected
    db.commit()

    assert onboarding_router.profile(FakeRequest("ana"), db).github_connected is True
    assert onboarding_router.profile(FakeRequest("bo"), db).github_connected is False
    assert onboarding_router.profile(FakeRequest(), db).github_connected is False
    guest = onboarding_router.submit_survey(SurveyAnswers(role="backend"), FakeRequest(), db)
    assert guest.github_connected is False
