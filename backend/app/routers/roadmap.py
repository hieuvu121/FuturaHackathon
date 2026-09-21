"""The three buckets. Owner: Track D."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..mock_store import load
from ..models.db import LearnerProfileRow, SkillStatusRow, User
from ..schemas.scores import SkillStatus
from ..schemas.roadmap import Buckets, RoadmapGraph
from ..services.knowledge import get_demand, get_taxonomy
from ..services.roadmap.buckets import build
from ..services.roadmap import review as roadmap_review
from ..services.roadmap import survey
from ..services.roadmap.concepts import graph_from_buckets, tailor
from ..services.roadmap.matcher import match
from ..services.portfolio import build_profile
from ..services.storage import get_owned_repo

router = APIRouter(prefix="/repos", tags=["roadmap"])


def _fixture_for(role: str) -> dict:
    """Mock roadmaps are keyed by role. An unknown role falls back to the first
    entry rather than to the whole mapping, which is not a Buckets payload."""
    fixture = load("roadmap")
    return fixture.get(role) or next(iter(fixture.values()))


@router.get("/portfolio/roadmap", response_model=Buckets)
def portfolio_roadmap(
    user: CurrentUser,
    db: DbDep,
    role: str = "backend",
    region: str = "AU",
) -> Buckets:
    settings = get_settings()
    if settings.mock_mode:
        return Buckets.model_validate(_fixture_for(role))
    try:
        skills = build_profile(db, user).scores.skills
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    taxonomy = get_taxonomy(settings)
    demand = match(skills, taxonomy, get_demand(settings), role, region)
    return build(skills, demand, role, region, taxonomy)


def _owner_id(db: DbDep | None, login: str) -> int | None:
    """None when there is nobody to look up, which is simply a roadmap with no history."""
    if db is None:
        return None
    return db.scalar(select(User.id).where(User.github_login == login))


def survey_graph(db: DbDep, owner_id: int | None, recall: dict) -> RoadmapGraph | None:
    """The roadmap for someone who came in through the survey, or None if they did not."""
    row = db.get(LearnerProfileRow, owner_id) if owner_id and db is not None else None
    if row is None or row.path != "survey" or not row.role:
        return None
    settings = get_settings()
    taxonomy = get_taxonomy(settings)
    path = survey.role_path(settings, taxonomy, row.role)
    if path is None:
        return None
    buckets = survey.buckets_for(path, list(row.known_skills or []), get_demand(settings))
    graph = graph_from_buckets(buckets, taxonomy, [], recall, from_survey=True)
    return graph.model_copy(update={"role_name": path.name})


@router.get("/portfolio/roadmap/graph", response_model=RoadmapGraph)
def portfolio_roadmap_graph(
    user: CurrentUser,
    db: DbDep,
    role: str = "software_engineer",
    region: str = "AU",
    include_hidden: bool = False,
) -> RoadmapGraph:
    """The same roadmap, regrouped into concepts for the diagram view.

    Grouping needs the taxonomy, which only exists here, so the frontend asks
    for concepts rather than reassembling them from a flat bucket list.

    Skills the user tailored out are left off, unless `include_hidden` asks for
    them back (flagged), which is what the tailoring view does.
    """
    settings = get_settings()
    taxonomy = get_taxonomy(settings)
    owner_id = _owner_id(db, user)
    recall = roadmap_review.recall_levels(db, owner_id) if owner_id else {}
    hidden = set(roadmap_review.review_row(db, owner_id).hidden_skills or []) if owner_id else set()
    if settings.mock_mode:
        # The survey works in mock mode too; without one, the fixture stands in for analysed code.
        graph = survey_graph(db, owner_id, recall) or graph_from_buckets(
            Buckets.model_validate(_fixture_for(role)), taxonomy, [], recall
        )
        return tailor(graph, hidden, keep_hidden=include_hidden)
    try:
        profile = build_profile(db, user)
    except LookupError as exc:
        # No analysed code. Someone who answered the survey still has a roadmap:
        # evidence wins when there is some, and the survey stands in when there is not.
        from_survey = survey_graph(db, owner_id, recall)
        if from_survey is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        return tailor(from_survey, hidden, keep_hidden=include_hidden)
    skills = profile.scores.skills
    demand = match(skills, taxonomy, get_demand(settings), role, region)
    buckets = build(skills, demand, role, region, taxonomy)
    # The scanner's findings are what let a next step name a real problem in
    # this user's code instead of offering a syllabus.
    # Drill results move the mastery bars, so the diagram reflects what recall
    # found rather than only what the repository suggested.
    graph = graph_from_buckets(buckets, taxonomy, profile.findings, recall)
    return tailor(graph, hidden, keep_hidden=include_hidden)


@router.get("/{repo_id}/roadmap", response_model=Buckets)
def roadmap(
    repo_id: str,
    user: CurrentUser,
    db: DbDep,
    role: str = "backend",
    region: str = "AU",
) -> Buckets:
    """Must return sensible output even when market frequency is None."""
    settings = get_settings()
    if settings.mock_mode:
        return Buckets.model_validate(_fixture_for(role))
    repo = get_owned_repo(db, repo_id, user)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    rows = db.scalars(
        select(SkillStatusRow).where(
            SkillStatusRow.user_id == repo.user_id,
            SkillStatusRow.repo_id == repo.id,
        )
    ).all()
    skills = [
        SkillStatus.model_validate(
            {"skill_id": row.skill_id, "tier": row.tier, "evidence": row.evidence or []}
        )
        for row in rows
    ]
    taxonomy = get_taxonomy(settings)
    demand = match(skills, taxonomy, get_demand(settings), role, region)
    return build(skills, demand, role, region, taxonomy)


# The final stage of the roadmap lives in its own module and is mounted here, so
# main.py -- which no feature branch edits -- never has to learn about it.
from .capstone import router as capstone_router  # noqa: E402
from .roadmap_review import router as review_router  # noqa: E402

router.include_router(capstone_router)
router.include_router(review_router)
