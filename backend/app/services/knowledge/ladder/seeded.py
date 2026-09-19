"""Reads knowledge_data/dimensions.yaml -- the team's own competency ladder."""

from ....config import Settings


class SeededLadder:
    def __init__(self, settings: Settings) -> None:
        self.path = settings.knowledge_data_dir / "dimensions.yaml"

    def levels(self, dimension: str) -> dict[int, str]:
        raise NotImplementedError

    def dimensions(self) -> list[str]:
        raise NotImplementedError

    def target_level(self, dimension: str, role: str, seniority: str) -> int:
        raise NotImplementedError
