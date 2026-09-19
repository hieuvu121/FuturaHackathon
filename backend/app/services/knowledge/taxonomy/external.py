"""Placeholder: Lightcast Open Skills / ESCO / O*NET / Australian Skills Classification."""

from ....config import Settings


class ExternalTaxonomy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def normalise(self, raw: str) -> str | None:
        raise NotImplementedError("Post-hackathon: bind to a standard taxonomy")

    def parents(self, skill_id: str) -> list[str]:
        raise NotImplementedError

    def name(self, skill_id: str) -> str:
        raise NotImplementedError
