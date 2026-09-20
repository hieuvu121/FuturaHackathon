"""A roadmap for someone with no repositories: built from a survey instead of from code.

The repository path reads evidence. A person who is just starting has none, so
they say which role they want and which of its skills they have already used,
and the roadmap starts from that role's path (knowledge_data/role_paths.yaml).

Two things keep this honest, because the product's whole argument is that
claims need evidence:

  * a skill the person SAYS they have used is "basics", never "verified", and it
    is asked about first in recall -- a belief nobody has checked is exactly
    what recall exists to test;
  * nothing here invents market numbers. Frequency comes from the configured
    demand source when it has the skill for that role, and is None otherwise.

From there on it is the same roadmap: the same stages, the same recall, the same
accept-or-dispute, and the same mastery bars once recall has tested a skill.
"""

import functools

import yaml
from pydantic import BaseModel, Field

from ...config import Settings
from ...schemas.market import MarketSkill
from ...schemas.roadmap import Bucket, Buckets, RoadmapItem
from ..knowledge.base import DemandSource, SkillTaxonomy

REGION = "AU"
SELF_REPORTED = "You said you have used this. Nothing has checked it yet, so recall asks about it first."
NOT_YET = "On the path to this role, and not something you have worked with yet."


class RoleSkill(BaseModel):
    skill_id: str
    name: str


class RolePath(BaseModel):
    id: str
    name: str
    summary: str = ""
    skills: list[RoleSkill] = Field(default_factory=list)


@functools.lru_cache(maxsize=2)
def _load(path: str) -> tuple[dict, ...]:
    payload = yaml.safe_load(open(path, encoding="utf-8").read()) or {}
    return tuple(payload.get("roles", []))


def role_paths(settings: Settings, taxonomy: SkillTaxonomy) -> list[RolePath]:
    """Every role, with its skills named. Ids the taxonomy does not know are left out."""
    paths: list[RolePath] = []
    for role in _load(str(settings.knowledge_data_dir / "role_paths.yaml")):
        skills: list[RoleSkill] = []
        for raw in role.get("skills", []):
            skill_id = taxonomy.normalise(str(raw))
            if skill_id is not None and skill_id not in {skill.skill_id for skill in skills}:
                skills.append(RoleSkill(skill_id=skill_id, name=taxonomy.name(skill_id)))
        paths.append(
            RolePath(id=role["id"], name=role["name"], summary=role.get("summary", ""), skills=skills)
        )
    return paths


def role_path(settings: Settings, taxonomy: SkillTaxonomy, role_id: str) -> RolePath | None:
    return next((path for path in role_paths(settings, taxonomy) if path.id == role_id), None)


def _market(demand: DemandSource | None, skill_id: str, role_id: str) -> MarketSkill | None:
    if demand is None:
        return None
    try:
        return demand.frequency(skill_id, role_id, REGION)
    except NotImplementedError:
        return None


def buckets_for(path: RolePath, known_skills: list[str], demand: DemandSource | None = None) -> Buckets:
    """The role path as a roadmap: what they say they know to revise, the rest to learn.

    Priority follows the path's order, so the first skill on it leads. Nothing is
    ever placed in `deepen`: that bucket means verified, and a survey verifies nothing.
    """
    known = set(known_skills)
    total = max(len(path.skills), 1)
    items: dict[Bucket, list[RoadmapItem]] = {Bucket.REVISE: [], Bucket.LEARN_NEW: []}
    for position, skill in enumerate(path.skills):
        bucket = Bucket.REVISE if skill.skill_id in known else Bucket.LEARN_NEW
        market = _market(demand, skill.skill_id, path.id)
        items[bucket].append(
            RoadmapItem(
                skill_id=skill.skill_id,
                skill_name=skill.name,
                bucket=bucket,
                reason=SELF_REPORTED if bucket is Bucket.REVISE else NOT_YET,
                evidence=[],
                market_frequency=market.frequency if market else None,
                provenance=market.provenance if market else None,
                # Earlier on the path matters more. Kept inside (0, 1].
                priority=round((total - position) / total, 4),
            )
        )
    return Buckets(
        role=path.id,
        region=REGION,
        revise=items[Bucket.REVISE],
        deepen=[],
        learn_new=items[Bucket.LEARN_NEW],
    )
