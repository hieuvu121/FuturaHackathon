"""Reads knowledge_data/skills.yaml -- 80-120 hand-curated skills with aliases."""

import re
import unicodedata

import yaml

from ....config import Settings


def _lookup_key(value: str) -> str:
    normalised = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[\s._-]+", " ", normalised)


class SeededTaxonomy:
    def __init__(self, settings: Settings) -> None:
        self.path = settings.knowledge_data_dir / "skills.yaml"
        payload = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        rows = payload.get("skills", []) if isinstance(payload, dict) else []

        self._skills: dict[str, dict] = {}
        self._lookup: dict[str, str] = {}
        for row in rows:
            skill_id = row["id"]
            if skill_id in self._skills:
                raise ValueError(f"Duplicate skill id: {skill_id}")
            self._skills[skill_id] = row

            for term in (skill_id, row["name"], *row.get("aliases", [])):
                key = _lookup_key(term)
                owner = self._lookup.get(key)
                if owner is not None and owner != skill_id:
                    raise ValueError(f"Ambiguous skill term {term!r}: {owner} and {skill_id}")
                self._lookup[key] = skill_id

    def normalise(self, raw: str) -> str | None:
        if not raw.strip():
            return None
        return self._lookup.get(_lookup_key(raw))

    def parents(self, skill_id: str) -> list[str]:
        return list(self._skills[skill_id].get("parents", []))

    def name(self, skill_id: str) -> str:
        return self._skills[skill_id]["name"]
