"""Community: shared roadmaps, and reviews whose weight depends on who wrote them."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.db import Base, CommunityCommentRow, CommunityRoadmapRow, SkillStatusRow, User
from app.routers import community as community_router
from app.routers import roadmap as roadmap_router
from app.schemas.community import NewComment, ShareRoadmap, Standing, Verdict
from app.services import community

MOCK = Settings(mock_mode=True, openai_api_key="", anthropic_api_key="")


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    for module in (community_router, roadmap_router):
        monkeypatch.setattr(module, "get_settings", lambda: MOCK)
    with Session(engine) as session:
        yield session


def _verified(db, login: str, count: int) -> User:
    user = User(github_login=login)
    db.add(user)
    db.flush()
    for index in range(count):
        db.add(SkillStatusRow(user_id=user.id, skill_id=f"skill_{index}", tier="verified", evidence=[]))
    db.commit()
    return user


def test_a_new_install_starts_with_labelled_samples_inserted_once(db):
    first = community_router.list_roadmaps("ana", db)
    second = community_router.list_roadmaps("ana", db)

    assert len(first) == len(second) == 2
    assert all(item.is_sample and not item.mine for item in first)
    junior = next(item for item in first if "junior" in item.title.casefold())
    assert junior.author == "mai-tran"
    assert [stage.title for stage in junior.stages][0] == "Learn first"
    # One mentor validates it, one experienced user suggests a change.
    assert (junior.validations, junior.suggestions, junior.comment_count) == (1, 1, 2)


def test_sharing_snapshots_the_roadmap_without_any_code_evidence(db):
    shared = community_router.share_roadmap(
        ShareRoadmap(title="  Backend   engineer  ", summary="Is this order right?"), "ana", db
    )

    assert shared.title == "Backend engineer"
    assert shared.author == "ana" and shared.mine and not shared.is_sample
    assert shared.stages and all(stage.concepts for stage in shared.stages)
    assert 0.0 <= shared.overall <= 1.0
    stored = db.get(CommunityRoadmapRow, shared.id).stages
    assert "evidence" not in str(stored) and ".py" not in str(stored)

    listed = community_router.list_roadmaps("ana", db)
    assert listed[0].id == shared.id  # newest first, ahead of the samples


def test_a_title_is_required_and_bounded():
    for bad in ("", "ab", "x" * 81):
        with pytest.raises(ValueError):
            ShareRoadmap(title=bad)
    with pytest.raises(ValueError):
        NewComment(body="x")


def test_standing_is_earned_or_granted_never_claimed(db, monkeypatch):
    newcomer = _verified(db, "newcomer", 0)
    nearly = _verified(db, "nearly", community.EXPERIENCED_AT - 1)
    seasoned = _verified(db, "seasoned", community.EXPERIENCED_AT)
    named = _verified(db, "Named-Mentor", 0)
    monkeypatch.setattr(community, "_community_file", lambda settings: {"mentors": ["named-mentor"]})

    assert community.standing_of(db, MOCK, newcomer) is Standing.MEMBER
    assert community.standing_of(db, MOCK, nearly) is Standing.MEMBER
    assert community.standing_of(db, MOCK, seasoned) is Standing.EXPERIENCED
    assert community.standing_of(db, MOCK, named) is Standing.MENTOR
    assert community.standing_of(db, MOCK, None) is Standing.MEMBER


def test_only_reviews_from_people_with_standing_move_the_validated_count(db):
    _verified(db, "seasoned", community.EXPERIENCED_AT)
    shared = community_router.share_roadmap(ShareRoadmap(title="Backend engineer"), "ana", db)

    community_router.comment(shared.id, NewComment(body="Looks right to me!", verdict=Verdict.VALIDATES), "newcomer", db)
    after_member = community_router.read_roadmap(shared.id, "ana", db)
    assert (after_member.validations, after_member.comment_count) == (0, 1)
    assert after_member.comments[0].standing is Standing.MEMBER

    community_router.comment(shared.id, NewComment(body="The order is sound.", verdict=Verdict.VALIDATES), "seasoned", db)
    detail = community_router.comment(
        shared.id, NewComment(body="Move SQL earlier.", verdict=Verdict.SUGGESTS), "seasoned", db
    )

    assert (detail.validations, detail.suggestions, detail.comment_count) == (1, 1, 3)
    assert [c.author for c in detail.comments] == ["newcomer", "seasoned", "seasoned"]
    assert detail.my_standing is Standing.EXPERIENCED
    assert [c.mine for c in detail.comments] == [False, True, True]


def test_nobody_can_validate_their_own_roadmap(db):
    _verified(db, "seasoned", community.EXPERIENCED_AT)
    shared = community_router.share_roadmap(ShareRoadmap(title="Platform engineer"), "seasoned", db)

    detail = community_router.comment(
        shared.id, NewComment(body="I think mine is great.", verdict=Verdict.VALIDATES), "seasoned", db
    )

    assert detail.comments[0].verdict is Verdict.COMMENT
    assert detail.validations == 0


def test_a_badge_stays_true_to_the_review_it_was_written_with(db):
    reviewer = _verified(db, "rising", 0)
    shared = community_router.share_roadmap(ShareRoadmap(title="Data engineer"), "ana", db)
    community_router.comment(shared.id, NewComment(body="Seems fine.", verdict=Verdict.VALIDATES), "rising", db)

    for index in range(community.EXPERIENCED_AT):
        db.add(SkillStatusRow(user_id=reviewer.id, skill_id=f"later_{index}", tier="verified", evidence=[]))
    db.commit()

    detail = community_router.read_roadmap(shared.id, "ana", db)
    assert detail.comments[0].standing is Standing.MEMBER
    assert detail.validations == 0


def test_comment_bodies_are_stored_as_plain_single_spaced_text(db):
    shared = community_router.share_roadmap(ShareRoadmap(title="Backend engineer"), "ana", db)

    detail = community_router.comment(
        shared.id, NewComment(body="  <script>alert(1)</script>\n\n  nice   roadmap "), "bo", db
    )

    # Stored verbatim as text; the page renders it as text, never as HTML.
    assert detail.comments[0].body == "<script>alert(1)</script> nice roadmap"


def test_only_the_author_can_take_a_roadmap_down_and_samples_stay(db):
    shared = community_router.share_roadmap(ShareRoadmap(title="Backend engineer"), "ana", db)
    community_router.comment(shared.id, NewComment(body="Good luck."), "bo", db)
    sample = next(item for item in community_router.list_roadmaps("ana", db) if item.is_sample)

    for roadmap_id, login in ((shared.id, "bo"), (sample.id, "ana")):
        with pytest.raises(Exception) as caught:
            community_router.delete_roadmap(roadmap_id, login, db)
        assert getattr(caught.value, "status_code", None) == 404

    community_router.delete_roadmap(shared.id, "ana", db)

    assert db.get(CommunityRoadmapRow, shared.id) is None
    assert db.query(CommunityCommentRow).filter_by(roadmap_id=shared.id).count() == 0
    with pytest.raises(Exception) as caught:
        community_router.read_roadmap(shared.id, "ana", db)
    assert getattr(caught.value, "status_code", None) == 404
