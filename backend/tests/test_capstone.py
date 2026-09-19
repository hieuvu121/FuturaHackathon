"""The roadmap's final stage: a derived brief, a submission, and a review that can be trusted."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.models.db import Base, CapstoneSubmissionRow, User
from app.routers import capstone as capstone_router
from app.schemas.capstone import RequirementVerdict, SubmissionStatus
from app.schemas.roadmap import Bucket, Buckets, RoadmapItem
from app.services.knowledge import get_taxonomy
from app.services.roadmap import capstone
from app.services.roadmap.capstone import (
    ReviewJudgement,
    build_brief,
    collect_files,
    parse_repo_url,
    review_submission,
    sample_review,
)
from app.services.roadmap.concepts import graph_from_buckets

SETTINGS = Settings(mock_mode=False, llm_provider="openai", openai_api_key="test-key")


def _item(skill_id: str, name: str, bucket: Bucket, priority: float = 0.5) -> RoadmapItem:
    return RoadmapItem(skill_id=skill_id, skill_name=name, bucket=bucket, reason="", priority=priority)


def _graph(recall=None):
    buckets = Buckets(
        role="software_engineer",
        region="AU",
        deepen=[_item("python", "Python", Bucket.DEEPEN)],
        revise=[
            _item("testing_unit", "Unit Testing", Bucket.REVISE),
            _item("git", "Git", Bucket.REVISE),
        ],
        learn_new=[
            _item("docker", "Docker", Bucket.LEARN_NEW, 0.9),
            _item("sql", "SQL", Bucket.LEARN_NEW, 0.4),
            _item("react", "React", Bucket.LEARN_NEW, 0.2),
        ],
    )
    return graph_from_buckets(buckets, get_taxonomy(SETTINGS), [], recall)


def _repo(tmp_path):
    root = tmp_path / "project"
    (root / "app").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "README.md").write_text("# Tracker\nRun with `make run`.\n", encoding="utf-8")
    (root / "app" / "main.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    (root / "tests" / "test_main.py").write_text("def test_handler():\n    assert True\n", encoding="utf-8")
    (root / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
    (root / "package-lock.json").write_text("{}", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG")
    return root


def test_brief_targets_the_open_parts_of_the_roadmap():
    brief = build_brief(_graph())

    # Written-but-unproven skills first, then the most useful new ones. Never the verified one.
    assert brief.target_skills == ["Git", "Unit Testing", "Docker", "SQL"]
    skill_requirements = [r for r in brief.requirements if r.skill_id]
    assert [r.skill_id for r in skill_requirements] == ["git", "testing_unit", "docker", "sql"]
    assert "Docker" in next(r.text for r in skill_requirements if r.skill_id == "docker")
    assert [r.id for r in brief.requirements if r.skill_id is None] == [
        "baseline_readme",
        "baseline_runs",
        "baseline_tests",
    ]
    assert "Git, Unit Testing, Docker and SQL" in brief.summary
    assert brief.deliverables


def test_brief_is_stable_and_reports_readiness():
    assert build_brief(_graph()) == build_brief(_graph())

    early = build_brief(_graph())
    assert early.ready is False
    assert "%" in early.readiness_note

    everything = {s: ({1, 2, 3, 4}, set()) for s in ("testing_unit", "git", "docker", "sql", "react")}
    assert build_brief(_graph(everything)).ready is True


def test_only_github_repository_urls_are_accepted():
    assert parse_repo_url("https://github.com/dev/tracker") == "dev/tracker"
    assert parse_repo_url(" https://github.com/dev/tracker.git/ ") == "dev/tracker"
    for bad in (
        "http://github.com/dev/tracker",
        "https://gitlab.com/dev/tracker",
        "https://github.com/dev",
        "https://github.com/dev/tracker/tree/main",
        "https://github.com/../tracker",
        "https://github.com/dev/tracker; rm -rf /",
        "file:///etc/passwd",
    ):
        with pytest.raises(ValueError):
            parse_repo_url(bad)


def test_collected_files_skip_dependencies_locks_and_binaries(tmp_path):
    tree, contents = collect_files(_repo(tmp_path))

    assert tree == ["README.md", "app/main.py", "tests/test_main.py"]
    # README and tests are read first, so they survive the size budget.
    assert list(contents) == ["README.md", "tests/test_main.py", "app/main.py"]


def test_review_counts_the_score_and_drops_files_that_do_not_exist(tmp_path, monkeypatch):
    brief = build_brief(_graph())
    prompts: list[str] = []

    def fake(settings, prompt):
        prompts.append(prompt)
        return ReviewJudgement.model_validate(
            {
                "summary": " A tidy small service. ",
                "strengths": ["Clear README", " "],
                "improvements": ["Test the failure paths"],
                "requirements": [
                    {
                        "requirement_id": "skill_git",
                        "verdict": "met",
                        "comment": "Small, explained commits.",
                        "files": ["README.md", "invented/file.py", "README.md"],
                    },
                    {"requirement_id": "baseline_tests", "verdict": "partial", "comment": "One test."},
                    {"requirement_id": "not_in_the_brief", "verdict": "met", "comment": "Ignored."},
                ],
            }
        )

    monkeypatch.setattr(capstone, "_request_review", fake)

    review = review_submission(SETTINGS, brief, _repo(tmp_path), notes="Built over a weekend.")

    by_id = {row.requirement_id: row for row in review.requirements}
    assert list(by_id) == [r.id for r in brief.requirements]
    assert by_id["skill_git"].files == ["README.md"]
    assert by_id["skill_docker"].verdict is RequirementVerdict.MISSING
    assert "did not address" in by_id["skill_docker"].comment
    # 1 met + 1 partial out of 7 requirements, counted here rather than asked of the model.
    assert review.score == round(1.5 / 7, 4)
    assert review.summary == "A tidy small service."
    assert review.strengths == ["Clear README"]
    assert review.files_reviewed == 3
    assert review.sample is False
    assert "Built over a weekend." in prompts[0]
    assert "def handler()" in prompts[0]


def test_an_empty_repository_is_refused_before_any_model_call(tmp_path, monkeypatch):
    monkeypatch.setattr(capstone, "_request_review", lambda *a: pytest.fail("model was called"))
    (tmp_path / "empty").mkdir()

    with pytest.raises(ValueError):
        review_submission(SETTINGS, build_brief(_graph()), tmp_path / "empty")


def test_sample_review_is_labelled_as_one():
    brief = build_brief(_graph())
    review = sample_review(brief)

    assert review.sample is True
    assert "Sample" in review.summary
    assert [row.requirement_id for row in review.requirements] == [r.id for r in brief.requirements]


def _session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _submission(factory, repo_url="https://github.com/dev/tracker") -> int:
    with factory() as db:
        db.add(User(id=1, github_login="dev", github_token="token"))
        row = CapstoneSubmissionRow(
            user_id=1, repo_url=repo_url, notes="", brief=build_brief(_graph()).model_dump(mode="json")
        )
        db.add(row)
        db.commit()
        return row.id


def test_background_review_clones_into_its_own_namespace_and_cleans_up(tmp_path, monkeypatch):
    factory = _session_factory()
    submission_id = _submission(factory)
    calls: list[tuple] = []
    root = _repo(tmp_path)

    monkeypatch.setattr(
        capstone_router.clone_service,
        "clone",
        lambda settings, user, name, token: calls.append(("clone", user, name, token)) or root,
    )
    monkeypatch.setattr(
        capstone_router.clone_service,
        "cleanup_repo",
        lambda settings, user, name: calls.append(("cleanup", user, name)),
    )
    monkeypatch.setattr(
        capstone,
        "_request_review",
        lambda settings, prompt: ReviewJudgement(summary="Fine.", requirements=[]),
    )

    capstone_router.run_review(submission_id, SETTINGS, factory)

    assert calls == [
        ("clone", "dev--capstone", "dev/tracker", "token"),
        ("cleanup", "dev--capstone", "dev/tracker"),
    ]
    with factory() as db:
        row = db.get(CapstoneSubmissionRow, submission_id)
        assert row.status == SubmissionStatus.REVIEWED.value
        assert row.review["summary"] == "Fine."


def test_a_failed_review_is_recorded_with_a_reason_and_still_cleans_up(tmp_path, monkeypatch):
    factory = _session_factory()
    submission_id = _submission(factory)
    cleaned: list[str] = []

    monkeypatch.setattr(capstone_router.clone_service, "clone", lambda *a: _repo(tmp_path))
    monkeypatch.setattr(
        capstone_router.clone_service, "cleanup_repo", lambda settings, user, name: cleaned.append(name)
    )

    def fail(settings, prompt):
        raise TimeoutError("provider timed out at 10.0.0.7")

    monkeypatch.setattr(capstone, "_request_review", fail)

    capstone_router.run_review(submission_id, SETTINGS, factory)

    with factory() as db:
        row = db.get(CapstoneSubmissionRow, submission_id)
        assert row.status == SubmissionStatus.FAILED.value
        assert "10.0.0.7" not in row.error
        assert row.review is None
    assert cleaned == ["dev/tracker"]


def test_mock_mode_reviews_without_cloning_or_calling_a_model(monkeypatch):
    factory = _session_factory()
    submission_id = _submission(factory)
    monkeypatch.setattr(capstone_router.clone_service, "clone", lambda *a: pytest.fail("cloned"))

    capstone_router.run_review(submission_id, Settings(mock_mode=True), factory)

    with factory() as db:
        row = db.get(CapstoneSubmissionRow, submission_id)
        assert row.status == SubmissionStatus.REVIEWED.value
        assert row.review["sample"] is True


def test_a_provider_refusal_is_explained_without_provider_detail():
    class RateLimitError(Exception):
        pass

    reason = capstone_router._reason(RateLimitError("429 credit_balance_exhausted org-123"))

    assert "AI reviewer is unavailable" in reason
    assert "org-123" not in reason
