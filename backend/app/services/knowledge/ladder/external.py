"""Placeholder for a standard framework such as SFIA."""

from ....config import Settings


class ExternalLadder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def levels(self, dimension: str) -> dict[int, str]:
        raise NotImplementedError("Post-hackathon: bind to SFIA")

    def dimensions(self) -> list[str]:
        raise NotImplementedError

    def metric_thresholds(self, dimension: str) -> dict[str, dict[int, str]]:
        raise NotImplementedError("Post-hackathon: bind to SFIA")

    def target_level(self, dimension: str, role: str, seniority: str) -> int:
        raise NotImplementedError
