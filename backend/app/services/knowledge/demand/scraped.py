"""Reads data/market.json, produced from data/jobs_raw/ job ads."""

from ....config import Settings
from ....schemas.market import MarketSkill


class ScrapedDemand:
    def __init__(self, settings: Settings) -> None:
        self.path = settings.data_dir / "market.json"

    def frequency(self, skill_id: str, role: str, region: str) -> MarketSkill | None:
        raise NotImplementedError

    def top_skills(self, role: str, region: str, limit: int) -> list[MarketSkill]:
        raise NotImplementedError
