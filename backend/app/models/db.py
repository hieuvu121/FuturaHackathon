"""SQLAlchemy tables. Owner: Track A.

DISTINCT from schemas/. Do not share classes between the two -- schemas are the
API contract, these are storage. Analyses hold repo_map / findings / scores as
JSON blobs so the pipeline can evolve without migrations during the hackathon.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from ..config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_login: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    github_token: Mapped[str | None] = mapped_column(Text, default=None)
    email: Mapped[str | None] = mapped_column(String(256), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(256), index=True)
    language: Mapped[str | None] = mapped_column(String(64), default=None)
    is_fork: Mapped[bool] = mapped_column(default=False)
    clone_path: Mapped[str | None] = mapped_column(Text, default=None)


class PortfolioRepo(Base):
    """The repositories currently selected as one user capability portfolio."""

    __tablename__ = "portfolio_repos"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    selected_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    repo_map: Mapped[dict | None] = mapped_column(JSON, default=None)
    findings: Mapped[list | None] = mapped_column(JSON, default=None)
    scores: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class QuestionRow(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    reference: Mapped[dict | None] = mapped_column(JSON, default=None)


class AnswerRow(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    submission: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    feedback: Mapped[str | None] = mapped_column(Text, default=None)


class RecallAttemptRow(Base):
    """One graded answer in the adaptive drill, in the order it happened.

    The loop's state is derived from this log rather than stored separately, so
    there is no session row to go stale or to reset by hand.
    """

    __tablename__ = "recall_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[str] = mapped_column(String(128))
    skill_id: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[int] = mapped_column(default=2)
    passed: Mapped[bool] = mapped_column(default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    submission: Mapped[str] = mapped_column(Text, default="")


class RoadmapReviewRow(Base):
    """Where one user stands with their roadmap: shown, accepted, or being redone.

    `recall_floor` is the id of the last recall attempt BEFORE the current
    session. Redoing the test raises it, so old answers stop counting without
    being deleted. `hidden_skills` is the user's own tailoring of the roadmap.
    """

    __tablename__ = "roadmap_reviews"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    recall_floor: Mapped[int] = mapped_column(Integer, default=0)
    hidden_skills: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class CapstoneSubmissionRow(Base):
    """One final-project submission and the review it received.

    The brief is stored with it: a review is against the requirements the user
    was given at the time, even if their roadmap has since moved on.
    """

    __tablename__ = "capstone_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    repo_url: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="reviewing")
    error: Mapped[str | None] = mapped_column(Text, default=None)
    brief: Mapped[dict] = mapped_column(JSON)
    review: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class CommunityRoadmapRow(Base):
    """A roadmap shared with the community, as it stood when it was shared.

    `stages` is a snapshot -- step titles, concept names and mastery only. No
    evidence, findings or file paths: sharing a roadmap must not publish code.
    `user_id` is null for the seeded samples, which carry `author_name` instead.
    """

    __tablename__ = "community_roadmaps"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, default=None)
    author_name: Mapped[str | None] = mapped_column(String(128), default=None)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text, default="")
    stages: Mapped[list] = mapped_column(JSON, default=list)
    overall: Mapped[float] = mapped_column(Float, default=0.0)
    is_sample: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class CommunityCommentRow(Base):
    """A review of a shared roadmap.

    `standing` is stamped when the comment is written, from what the author had
    earned at that moment, so a badge shown beside an old review stays true to
    the review rather than drifting with the author's later progress.
    """

    __tablename__ = "community_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    roadmap_id: Mapped[int] = mapped_column(ForeignKey("community_roadmaps.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, default=None)
    author_name: Mapped[str | None] = mapped_column(String(128), default=None)
    standing: Mapped[str] = mapped_column(String(16), default="member")
    verdict: Mapped[str] = mapped_column(String(16), default="comment")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class SkillStatusRow(Base):
    __tablename__ = "skill_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    repo_id: Mapped[int | None] = mapped_column(ForeignKey("repos.id"), default=None)
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    tier: Mapped[str] = mapped_column(String(16), default="touched")
    evidence: Mapped[list | None] = mapped_column(JSON, default=None)


def init_db() -> None:
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
