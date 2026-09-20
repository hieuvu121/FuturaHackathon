"""The first step: connect repositories, or answer a survey.

  GET  /onboarding/roles     the roles a survey can aim at, with the skills on each path
  GET  /onboarding/profile   which way this visitor came in, if they have chosen yet
  POST /onboarding/survey    "I have no repositories": pick a role, say what you have used

Someone with no repositories may well have no GitHub account either, so the
survey must not demand a login. Submitting it without a session creates a guest
user and signs them in. Everything downstream -- recall, the roadmap, accepting
or disputing it -- then works for them exactly as it does for anyone else.
"""

import secrets

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import DbDep
from ..models.db import LearnerProfileRow, User
from ..services.knowledge import get_taxonomy
from ..services.roadmap import review as roadmap_review
from ..services.roadmap import survey

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

GUEST_PREFIX = "guest-"
MOCK_USER = "demo-user"


class SurveyAnswers(BaseModel):
    role: str = Field(min_length=1, max_length=64)
    known_skills: list[str] = Field(default_factory=list, max_length=60)


class LearnerProfile(BaseModel):
    """How this person came in. `path` is None until they have chosen."""

    path: str | None = Field(None, description="'survey' or 'repos'")
    role: str | None = None
    role_name: str | None = None
    known_skills: list[str] = Field(default_factory=list)
    user: str | None = None
    guest: bool = False
    github_connected: bool = Field(
        False, description="A GitHub token is on file. False for guests, and after GitHub rejected the last one."
    )


def _session_login(request: Request) -> str | None:
    if get_settings().mock_mode:
        return MOCK_USER
    return request.session.get("user")


def _user(db: Session, login: str) -> User:
    owner = db.scalar(select(User).where(User.github_login == login))
    if owner is None:
        owner = User(github_login=login)
        db.add(owner)
        db.commit()
        db.refresh(owner)
    return owner


def _to_schema(
    row: LearnerProfileRow | None, login: str | None, role_name: str | None, owner: User | None = None
) -> LearnerProfile:
    return LearnerProfile(
        github_connected=bool(owner and owner.github_token),
        path=row.path if row else None,
        role=row.role if row else None,
        role_name=role_name,
        known_skills=list(row.known_skills or []) if row else [],
        user=login,
        guest=bool(login and login.startswith(GUEST_PREFIX)),
    )


@router.get("/roles", response_model=list[survey.RolePath])
def roles() -> list[survey.RolePath]:
    settings = get_settings()
    return survey.role_paths(settings, get_taxonomy(settings))


@router.get("/profile", response_model=LearnerProfile)
def profile(request: Request, db: DbDep) -> LearnerProfile:
    """Never a 401: a visitor who has not chosen yet simply has no path."""
    login = _session_login(request)
    if login is None:
        return LearnerProfile()
    owner = db.scalar(select(User).where(User.github_login == login))
    row = db.get(LearnerProfileRow, owner.id) if owner else None
    settings = get_settings()
    path = survey.role_path(settings, get_taxonomy(settings), row.role) if row and row.role else None
    return _to_schema(row, login, path.name if path else None, owner)


@router.post("/survey", response_model=LearnerProfile, status_code=status.HTTP_201_CREATED)
def submit_survey(answers: SurveyAnswers, request: Request, db: DbDep) -> LearnerProfile:
    settings = get_settings()
    taxonomy = get_taxonomy(settings)
    path = survey.role_path(settings, taxonomy, answers.role)
    if path is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose one of the listed roles")

    login = _session_login(request)
    if login is None:
        login = f"{GUEST_PREFIX}{secrets.token_hex(5)}"
        request.session["user"] = login
    owner = _user(db, login)

    # Only skills that are actually on the chosen path count as "used": the
    # survey shows that list, so anything else did not come from the form.
    on_path = {skill.skill_id for skill in path.skills}
    known = sorted({skill for skill in answers.known_skills if skill in on_path})

    row = db.get(LearnerProfileRow, owner.id)
    if row is None:
        row = LearnerProfileRow(user_id=owner.id)
        db.add(row)
    row.path = "survey"
    row.role = path.id
    row.known_skills = known
    db.commit()

    # A new survey is a new starting point: recall begins again, and the roadmap
    # it produces has to be agreed to afresh.
    roadmap_review.restart_recall(db, owner.id)
    return _to_schema(row, login, path.name, owner)
