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
