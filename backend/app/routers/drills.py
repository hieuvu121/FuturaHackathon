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
from ..schemas.recall import (
    AdaptiveGrade,
    Answer,
    NextQuestion,
    PracticeGrade,
    Question,
    QuestionType,
)
from ..schemas.roadmap import NodeStatus
from ..schemas.scores import Tier
from ..services.knowledge import get_demand, get_taxonomy
from ..services.portfolio import build_profile, owned_selected_repos
from ..services.recall.adaptive import Attempt, BankEntry, entry_for, next_question
from ..services.recall import practice
from ..services.recall.drills import PASS_MARK, grade_drill, model_answer
from ..services.recall.repo_drills import ensure_repo_drills, load_repo_entries, repo_entry_for
from ..services.roadmap import review as roadmap_review
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


def _survey_order(db: DbDep, login: str) -> list[tuple[str, str]]:
    """Skills to probe for someone with no analysed code: what they SAID they know
    first -- that is the unchecked belief -- then the rest of their role's path."""
    from .roadmap import survey_graph  # roadmap.py imports nothing from here; kept local for symmetry

    owner = db.scalar(select(User).where(User.github_login == login))
    graph = survey_graph(db, owner.id if owner else None, {})
    if graph is None:
        return []
    nodes = [node for concept in graph.concepts for node in concept.skills]
    nodes.sort(key=lambda node: (0 if node.status is NodeStatus.FAMILIAR else 1, -node.priority))
    return [(node.skill_id, node.skill_name) for node in nodes]


def _attempts(db: DbDep, user: User) -> list[Attempt]:
    """This session's answers. A restarted test leaves the older ones behind."""
    rows = roadmap_review.session_attempts(db, user.id)
    return [Attempt(r.skill_id, r.level, r.passed, r.question_id) for r in rows]


# What kind of question each of the five slots would like to be. It opens with
# a coding task -- on the user's own code when one has been written for them --
# and alternates, so a session is never all theory or all typing.
SESSION_MIX: tuple[QuestionType, ...] = (
    QuestionType.CODING,
    QuestionType.CONCEPT,
    QuestionType.EXPLAIN,
    QuestionType.CONCEPT,
    QuestionType.CODING,
)


def _step(settings, attempts: list[Attempt], order, repo_drills) -> NextQuestion:
    """The next question, or the end of the session once five have been answered.

    Five is enough to place the two or three skills the roadmap cares most
    about, and short enough that people finish. The roadmap is drawn from
    whatever those five found.
    """
    if len(attempts) >= roadmap_review.SESSION_LENGTH:
        return NextQuestion(question=None, asked=len(attempts), remaining_skills=0)
    return next_question(settings, attempts, order, repo_drills, SESSION_MIX[len(attempts)])


def _session(
    db: DbDep, login: str, generate: bool = False
) -> tuple[list[tuple[str, str]], tuple[BankEntry, ...]]:
    """Skills to probe, in the roadmap's own priority, plus the user's repository drills.

    What the user has written but never had checked comes first: that is where
    an unfounded belief is most likely hiding, which is what recall is for.
    New skills follow, so a session can still teach something once the
    familiar ones are mapped.

    `generate` writes the missing repository drills first. Only `next` asks for
    that: it is the call the page already waits on, whereas grading must stay quick.
    """
    settings = get_settings()
    if settings.mock_mode:
        return _survey_order(db, login) or list(MOCK_SKILL_ORDER), ()
    try:
        profile = build_profile(db, login)
    except LookupError:
        return _survey_order(db, login), ()
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
    order = [(node.skill_id, node.skill_name) for node in ordered]
    repos = owned_selected_repos(db, login)
    if generate:
        return order, ensure_repo_drills(db, settings, login, skills, repos, order)
    return order, load_repo_entries(db, [repo.id for repo in repos])


@router.get("/next", response_model=NextQuestion)
def next_drill(user: CurrentUser, db: DbDep) -> NextQuestion:
    """The question to ask now, given everything answered so far."""
    settings = get_settings()
    order, repo_drills = _session(db, user, generate=True)
    if not order:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No analysed repositories to build a session from"
        )
    return _step(settings, _attempts(db, _user(db, user)), order, repo_drills)


@router.post("/answer", response_model=AdaptiveGrade)
def answer_drill(answer: Answer, user: CurrentUser, db: DbDep) -> AdaptiveGrade:
    """Grade one drill, record it, and return the question it earned."""
    settings = get_settings()
    owner = _user(db, user)
    entry = entry_for(settings, answer.question_id) or repo_entry_for(
        db, [repo.id for repo in owned_selected_repos(db, user)], answer.question_id
    )
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    if len(_attempts(db, owner)) >= roadmap_review.SESSION_LENGTH:
        raise HTTPException(status.HTTP_409_CONFLICT, "This recall session is already complete")

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

    upcoming = _step(settings, _attempts(db, owner), *_session(db, user))
    if upcoming.question is None:
        # The answers just changed the roadmap, so it has to be agreed to again.
        roadmap_review.mark_pending(db, owner.id)
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


# --- Practice ---------------------------------------------------------------------
# The second half of recall. The evaluation above finds the user's level and
# feeds the roadmap; practice is where they go afterwards to work on a topic.
# It records nothing and promotes nothing, so there is no session to finish.


@router.get("/practice/topics", response_model=list[practice.PracticeTopic])
def practice_topics(user: CurrentUser) -> list[practice.PracticeTopic]:
    return practice.topics(get_settings())


@router.get("/practice/{skill_id}/questions", response_model=list[Question])
def practice_questions(
    skill_id: str, user: CurrentUser, kind: QuestionType | None = None
) -> list[Question]:
    """A topic's questions, optionally of one kind: concept, coding or explain."""
    found = practice.questions(get_settings(), skill_id, kind)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No practice questions for this topic")
    return found


@router.post("/practice/answer", response_model=PracticeGrade)
def practice_answer(answer: Answer, user: CurrentUser) -> PracticeGrade:
    settings = get_settings()
    entry = practice.entry_for(settings, answer.question_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    verdict = grade_drill(settings, entry, answer)
    return PracticeGrade(
        question_id=entry.question.id,
        passed=verdict.score >= PASS_MARK,
        score=round(verdict.score, 4),
        feedback=verdict.feedback,
        missing=verdict.missing,
        model_answer=model_answer(entry),
    )

