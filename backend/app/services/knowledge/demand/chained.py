"""Tries several demand sources in order, taking the first that answers.

This is what lets the team defer the source-of-truth decision without blocking
anyone: set DEMAND_CHAIN=scraped,llm,seeded and the roadmap uses real scraped
data where it exists, an LLM estimate where it does not, and the hand-written
table as the floor.

Each row keeps the provenance of the source that actually answered, so a mixed
roadmap still shows the user which figures are measured and which are guessed.
"""

from ....config import Settings
from ....schemas.market import MarketSkill


class ChainedDemand:
    def __init__(self, settings: Settings, sources: list) -> None:
        self.settings = settings
        self.sources = sources

    def frequency(self, skill_id: str, role: str, region: str) -> MarketSkill | None:
        for source in self.sources:
            hit = source.frequency(skill_id, role, region)
            if hit is not None:
                return hit
        return None  # legitimate. buckets.py ranks on proximity alone.

    def top_skills(self, role: str, region: str, limit: int) -> list[MarketSkill]:
        raise NotImplementedError("Track D: merge by skill_id, first source wins")
