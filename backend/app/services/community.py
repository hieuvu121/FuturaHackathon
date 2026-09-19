"""Community: share a roadmap under a role title, and have it reviewed.

The idea is peer validation with a filter on whose word counts. Anyone may
comment. Only a review from someone with standing -- a mentor the platform
names, or a user who has verified enough skills of their own -- moves a
roadmap's "validated" count. Standing is looked up here from things the user
cannot simply type in, which is the whole point of showing a badge.

A shared roadmap is a SNAPSHOT. Reviews are about the roadmap as it was when it
was shared; the author's live roadmap moving on must not rewrite what reviewers
were responding to.
"""

import functools

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models.db import CommunityCommentRow, CommunityRoadmapRow, SkillStatusRow, User
from ..schemas.community import (
    CommunityComment,
    CommunityRoadmap,
    CommunityRoadmapDetail,
    SharedConcept,
    SharedStage,
    Standing,
    Verdict,
)
from ..schemas.roadmap import RoadmapGraph

# How many verified skills make a reviewer "experienced". Verified means recall
# confirmed it, so this cannot be reached by connecting a big repository alone.
EXPERIENCED_AT = 3
WEIGHTED = (Standing.MENTOR, Standing.EXPERIENCED)


@functools.lru_cache(maxsize=2)
def _config(path: str) -> dict:
    return yaml.safe_load(open(path, encoding="utf-8").read()) or {}


def _community_file(settings: Settings) -> dict:
    return _config(str(settings.knowledge_data_dir / "community.yaml"))


def standing_of(db: Session, settings: Settings, user: User | None) -> Standing:
    if user is None:
        return Standing.MEMBER
    mentors = {str(login).casefold() for login in _community_file(settings).get("mentors", [])}
    if user.github_login.casefold() in mentors:
        return Standing.MENTOR
    verified = db.scalar(
        select(func.count(func.distinct(SkillStatusRow.skill_id))).where(
            SkillStatusRow.user_id == user.id, SkillStatusRow.tier == "verified"
        )
    )
    return Standing.EXPERIENCED if (verified or 0) >= EXPERIENCED_AT else Standing.MEMBER


def snapshot(graph: RoadmapGraph) -> tuple[list[dict], float]:
    """The shape of a roadmap worth reviewing: steps, concepts, and how far along each is.

    Evidence, findings and file paths are deliberately left out. Sharing a
    roadmap must not publish the user's code or what the scanner said about it.
    """
    by_id = {concept.concept_id: concept for concept in graph.concepts}
    stages = [
        SharedStage(
            title=stage.title,
            concepts=[
                SharedConcept(name=by_id[cid].concept_name, mastery=by_id[cid].mastery)
                for cid in stage.concept_ids
                if cid in by_id
            ],
        )
        for stage in graph.stages
    ]
    skills = [skill for concept in graph.concepts for skill in concept.skills if not skill.hidden]
    overall = sum(skill.mastery for skill in skills) / len(skills) if skills else 0.0
    return [stage.model_dump(mode="json") for stage in stages if stage.concepts], round(overall, 4)


def ensure_samples(db: Session, settings: Settings) -> None:
    """Insert the sample roadmaps once, so a new install has something to read."""
    if db.scalar(select(func.count()).select_from(CommunityRoadmapRow).where(CommunityRoadmapRow.is_sample)):
        return
    for sample in _community_file(settings).get("samples", []):
        row = CommunityRoadmapRow(
            user_id=None,
            author_name=sample["author"],
            title=sample["title"],
            summary=" ".join(str(sample.get("summary", "")).split()),
            stages=sample.get("stages", []),
            overall=float(sample.get("overall", 0.0)),
            is_sample=True,
        )
        db.add(row)
        db.flush()
        for comment in sample.get("comments", []):
            db.add(
                CommunityCommentRow(
                    roadmap_id=row.id,
                    user_id=None,
                    author_name=comment["author"],
                    standing=Standing(comment.get("standing", "member")).value,
                    verdict=Verdict(comment.get("verdict", "comment")).value,
                    body=" ".join(str(comment["body"]).split()),
                )
            )
    db.commit()


def _author(db: Session, row: CommunityRoadmapRow | CommunityCommentRow) -> str:
    if row.user_id is None:
        return row.author_name or "someone"
    owner = db.get(User, row.user_id)
    return owner.github_login if owner else "someone"


def _tally(db: Session, roadmap_id: int) -> tuple[int, int, int]:
    rows = db.execute(
        select(CommunityCommentRow.standing, CommunityCommentRow.verdict).where(
            CommunityCommentRow.roadmap_id == roadmap_id
        )
    ).all()
    weighted = {standing.value for standing in WEIGHTED}
    validations = sum(1 for s, v in rows if s in weighted and v == Verdict.VALIDATES.value)
    suggestions = sum(1 for s, v in rows if s in weighted and v == Verdict.SUGGESTS.value)
    return validations, suggestions, len(rows)


def to_roadmap(db: Session, settings: Settings, row: CommunityRoadmapRow, viewer: User | None) -> CommunityRoadmap:
    validations, suggestions, count = _tally(db, row.id)
    author = db.get(User, row.user_id) if row.user_id else None
    return CommunityRoadmap(
        id=row.id,
        title=row.title,
        summary=row.summary or "",
        author=_author(db, row),
        author_standing=standing_of(db, settings, author),
        overall=row.overall or 0.0,
        stages=[SharedStage.model_validate(stage) for stage in row.stages or []],
        validations=validations,
        suggestions=suggestions,
        comment_count=count,
        is_sample=bool(row.is_sample),
        mine=viewer is not None and row.user_id == viewer.id,
        created_at=row.created_at,
    )


def to_detail(db: Session, settings: Settings, row: CommunityRoadmapRow, viewer: User | None) -> CommunityRoadmapDetail:
    comments = db.scalars(
        select(CommunityCommentRow)
        .where(CommunityCommentRow.roadmap_id == row.id)
        .order_by(CommunityCommentRow.id)
    ).all()
    return CommunityRoadmapDetail(
        **to_roadmap(db, settings, row, viewer).model_dump(),
        my_standing=standing_of(db, settings, viewer),
        comments=[
            CommunityComment(
                id=comment.id,
                author=_author(db, comment),
                standing=Standing(comment.standing),
                verdict=Verdict(comment.verdict),
                body=comment.body,
                created_at=comment.created_at,
                mine=viewer is not None and comment.user_id == viewer.id,
            )
            for comment in comments
        ],
    )


def add_comment(
    db: Session, settings: Settings, row: CommunityRoadmapRow, author: User, body: str, verdict: Verdict
) -> CommunityCommentRow:
    """Store a review. The badge is stamped now, from what the author has earned today.

    An author replying on their own roadmap can only comment: validating your
    own roadmap would make the count meaningless.
    """
    if row.user_id == author.id:
        verdict = Verdict.COMMENT
    comment = CommunityCommentRow(
        roadmap_id=row.id,
        user_id=author.id,
        standing=standing_of(db, settings, author).value,
        verdict=verdict.value,
        body=" ".join(body.split()),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment
