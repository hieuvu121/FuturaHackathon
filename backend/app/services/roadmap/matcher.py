"""Normalises user skills and joins them to demand. Owner: Track D."""

from ...schemas.market import MarketSkill
from ...schemas.scores import SkillStatus
from ..knowledge.base import DemandSource, SkillTaxonomy


def match(
    skills: list[SkillStatus], taxonomy: SkillTaxonomy, demand: DemandSource, role: str, region: str
) -> dict[str, MarketSkill | None]:
    """skill_id -> demand row, or None when the source has no data for it."""
    raise NotImplementedError
