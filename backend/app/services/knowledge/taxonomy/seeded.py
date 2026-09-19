"""Reads knowledge_data/skills.yaml -- 80-120 hand-curated skills with aliases."""

from ....config import Settings


class SeededTaxonomy:
    def __init__(self, settings: Settings) -> None:
        self.path = settings.knowledge_data_dir / "skills.yaml"

    def normalise(self, raw: str) -> str | None:
        raise NotImplementedError

    def parents(self, skill_id: str) -> list[str]:
        raise NotImplementedError

    def name(self, skill_id: str) -> str:
        raise NotImplementedError
