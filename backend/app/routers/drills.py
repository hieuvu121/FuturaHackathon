"""The adaptive drill loop. Owner: Track B.

Two endpoints and no session object: `next` derives where to go from the
attempt log, and `answer` grades, records, and hands back the question the
answer earned. Refreshing the page therefore resumes rather than restarts.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..models.db import RecallAttemptRow, SkillStatusRow, User
from ..schemas.recall import AdaptiveGrade, Answer, NextQuestion
from ..schemas.roadmap import NodeStatus
from ..schemas.scores import Tier
from ..services.knowledge import get_demand, get_taxonomy
from ..services.portfolio import build_profile
from ..services.recall.adaptive import Attempt, entry_for, next_question
from ..services.recall.drills import PASS_MARK, grade_drill, model_answer
from ..services.roadmap.buckets import build
from ..services.roadmap.concepts import graph_from_buckets
from ..services.roadmap.matcher import match

router = APIRouter(prefix="/recall", tags=["recall"])
logger = logging.getLogger(__name__)

# A drill cleared at this level or above is treated as understanding the skill,
# not merely recognising it -- the same bar the generated transfer question sets.
VERIFY_LEVEL = 3


# What a mock-mode session drills. Enough breadth to show the loop moving
# between skills without needing an analysed repository behind it.
MOCK_SKILL_ORDER: list[tuple[str, str]] = [
    ("data_modelling", "Data Modelling"),
    ("clean_code", "Clean Code"),
    ("testing_unit", "Unit Testing"),
    ("python", "Python"),
    ("git", "Git"),
]


def _user(db: DbDep, login: str) -> User:
    user = db.scalar(select(User).where(User.github_login == login))
    if user is None:
        if not get_settings().mock_mode:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        # Mock mode has no OAuth round trip, so the demo user may not exist yet.
        # The attempt log is what drives the loop, so it still needs somewhere
        # to hang.
        user = User(github_login=login)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _attempts(db: DbDep, user: User) -> list[Attempt]:
    rows = db.scalars(
        select(RecallAttemptRow)
        .where(RecallAttemptRow.user_id == user.id)
        .order_by(RecallAttemptRow.id)
    ).all()
    return [Attempt(r.skill_id, r.level, r.passed, r.question_id) for r in rows]


def _skill_order(db: DbDep, login: str) -> list[tuple[str, str]]:
    """Skills to probe, in the roadmap's own priority.

    What the user has written but never had checked comes first: that is where
    an unfounded belief is most likely hiding, which is what recall is for.
    New skills follow, so a session can still teach something once the
    familiar ones are mapped.
    """
    settings = get_settings()
    if settings.mock_mode:
        return list(MOCK_SKILL_ORDER)
    try:
        profile = build_profile(db, login)
    except LookupError:
        return []
    taxonomy = get_taxonomy(settings)
    skills = profile.scores.skills
    demand = match(skills, taxonomy, get_demand(settings), "software_engineer", "AU")
    graph = graph_from_buckets(
        build(skills, demand, "software_engineer", "AU", taxonomy), taxonomy, profile.findings
    )
    nodes = [node for concept in graph.concepts for node in concept.skills]
    ordered = sorted(
        nodes,
        key=lambda node: (
            0 if node.status is NodeStatus.FAMILIAR else 1 if node.status is NodeStatus.VERIFIED else 2,
            -node.priority,
        ),
    )
    return [(node.skill_id, node.skill_name) for node in ordered]


@router.get("/next", response_model=NextQuestion)
def next_drill(user: CurrentUser, db: DbDep) -> NextQuestion:
    """The question to ask now, given everything answered so far."""
    settings = get_settings()
    order = _skill_order(db, user)
    if not order:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No analysed repositories to build a session from"
        )
    return next_question(settings, _attempts(db, _user(db, user)), order)


@router.post("/answer", response_model=AdaptiveGrade)
def answer_drill(answer: Answer, user: CurrentUser, db: DbDep) -> AdaptiveGrade:
    """Grade one drill, record it, and return the question it earned."""
    settings = get_settings()
    entry = entry_for(settings, answer.question_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")

    owner = _user(db, user)
    verdict = grade_drill(settings, entry, answer)
    passed = verdict.score >= PASS_MARK
    skill_id = entry.question.skill_ids[0]

    db.add(
        RecallAttemptRow(
            user_id=owner.id,
            question_id=entry.question.id,
            skill_id=skill_id,
            level=entry.question.level,
            passed=passed,
            score=verdict.score,
            submission=answer.submission,
        )
    )
    db.commit()

    tier_change: dict[str, Tier] = {}
    if passed and entry.question.level >= VERIFY_LEVEL:
        rows = db.scalars(
            select(SkillStatusRow).where(
                SkillStatusRow.user_id == owner.id, SkillStatusRow.skill_id == skill_id
            )
        ).all()
        for row in rows:
            row.tier = Tier.VERIFIED.value
        if rows:
            db.commit()
            tier_change[skill_id] = Tier.VERIFIED

    upcoming = next_question(settings, _attempts(db, owner), _skill_order(db, user))
    return AdaptiveGrade(
        question_id=entry.question.id,
        passed=passed,
        score=round(verdict.score, 4),
        feedback=verdict.feedback,
        tier_change=tier_change,
        level=entry.question.level,
        next_level=upcoming.question.level if upcoming.question else None,
        model_answer=model_answer(entry),
        next=upcoming,
    )
