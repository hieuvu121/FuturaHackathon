"""Assigns and ranks the three buckets. Owner: Track D.

  Revise    = touched, not verified
  Deepen    = touched AND verified
  Learn New = never touched, in demand

Ranked by job-ad frequency weighted by proximity to what was already touched.
MUST produce a sensible ordering when frequency is None -- fall back to
proximity alone rather than dropping the item or crashing.
"""

from ...schemas.market import MarketSkill
from ...schemas.roadmap import Buckets
from ...schemas.scores import SkillStatus


def build(
    skills: list[SkillStatus], demand: dict[str, MarketSkill | None], role: str, region: str
) -> Buckets:
    raise NotImplementedError
