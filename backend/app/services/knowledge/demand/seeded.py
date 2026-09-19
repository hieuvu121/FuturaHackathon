"""Hand-written frequencies. Exists so the demo never depends on a scraper."""

from ....config import Settings
from ....schemas.market import MarketSkill


class SeededDemand:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def frequency(self, skill_id: str, role: str, region: str) -> MarketSkill | None:
        raise NotImplementedError

    def top_skills(self, role: str, region: str, limit: int) -> list[MarketSkill]:
        raise NotImplementedError
