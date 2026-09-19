"""Hand-written frequencies. Exists so the demo never depends on a scraper."""

import json

from ....config import Settings
from ....schemas.market import MarketSkill


class SeededDemand:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.data_dir / "market.json"
        if self.path.is_file():
            rows = json.loads(self.path.read_text(encoding="utf-8"))
            self._skills = [MarketSkill.model_validate(row) for row in rows]
        else:
            self._skills = []

    def frequency(self, skill_id: str, role: str, region: str) -> MarketSkill | None:
        role_key = role.casefold().strip()
        region_key = region.casefold().strip()
        return next(
            (
                skill
                for skill in self._skills
                if skill.skill_id == skill_id
                and skill.role.casefold() == role_key
                and skill.region.casefold() == region_key
            ),
            None,
        )

    def top_skills(self, role: str, region: str, limit: int) -> list[MarketSkill]:
        if limit <= 0:
            return []

        role_key = role.casefold().strip()
        region_key = region.casefold().strip()
        matches = [
            skill
            for skill in self._skills
            if skill.role.casefold() == role_key and skill.region.casefold() == region_key
        ]
        return sorted(
            matches,
            key=lambda skill: (
                skill.frequency is None,
                -(skill.frequency or 0.0),
                skill.skill_id,
            ),
        )[:limit]
