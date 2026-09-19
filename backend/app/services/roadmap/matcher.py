"""Normalises user skills and joins them to demand. Owner: Track D."""

from ...schemas.market import MarketSkill
from ...schemas.scores import SkillStatus
from ..knowledge.base import DemandSource, SkillTaxonomy


def match(
    skills: list[SkillStatus], taxonomy: SkillTaxonomy, demand: DemandSource, role: str, region: str
) -> dict[str, MarketSkill | None]:
    """Return canonical known skills plus unseen demand candidates."""
    matched: dict[str, MarketSkill | None] = {}
    for status in skills:
        skill_id = taxonomy.normalise(status.skill_id)
        if skill_id is None or skill_id in matched:
            continue
        try:
            matched[skill_id] = demand.frequency(skill_id, role, region)
        except NotImplementedError:
            matched[skill_id] = None

    try:
        candidates = demand.top_skills(role, region, limit=25)
    except NotImplementedError:
        candidates = []

    for candidate in candidates:
        skill_id = taxonomy.normalise(candidate.skill_id)
        if skill_id is None:
            continue
        canonical = candidate.model_copy(update={"skill_id": skill_id})
        if skill_id not in matched or matched[skill_id] is None:
            matched[skill_id] = canonical
    return matched
