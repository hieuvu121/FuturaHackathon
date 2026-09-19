"""Reads knowledge_data/dimensions.yaml -- the team's own competency ladder."""

import yaml

from ....config import Settings


class SeededLadder:
    def __init__(self, settings: Settings) -> None:
        self.path = settings.knowledge_data_dir / "dimensions.yaml"
        payload = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        rows = payload.get("dimensions", []) if isinstance(payload, dict) else []
        self._dimensions = {row["id"]: row for row in rows}
        if len(self._dimensions) != len(rows):
            raise ValueError("Duplicate dimension id in dimensions.yaml")

    def levels(self, dimension: str) -> dict[int, str]:
        return dict(self._dimensions[dimension]["levels"])

    def dimensions(self) -> list[str]:
        return list(self._dimensions)

    def metric_thresholds(self, dimension: str) -> dict[str, dict[int, str]]:
        return {
            metric: dict(levels)
            for metric, levels in self._dimensions[dimension]["metric_thresholds"].items()
        }

    def target_level(self, dimension: str, role: str, seniority: str) -> int:
        if dimension not in self._dimensions:
            raise KeyError(dimension)
        seniority_key = seniority.casefold().strip()
        if any(term in seniority_key for term in ("lead", "staff", "principal", "senior")):
            return 4
        if any(term in seniority_key for term in ("junior", "graduate", "entry")):
            return 2
        return 3
