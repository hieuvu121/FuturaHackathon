"""Contract tests for the seeded taxonomy and demand implementations."""

import json
from pathlib import Path

import pytest

from app.config import Settings, get_settings
from app.services.knowledge.demand.seeded import SeededDemand
from app.services.knowledge.taxonomy.seeded import SeededTaxonomy


def test_taxonomy_normalises_ids_names_aliases_and_separators():
    taxonomy = SeededTaxonomy(get_settings())

    assert taxonomy.normalise("python") == "python"
    assert taxonomy.normalise("  PYTHON  ") == "python"
    assert taxonomy.normalise("React.JS") == "react"
    assert taxonomy.normalise("object_oriented_programming") == "object_oriented_programming"
    assert taxonomy.normalise("not a real skill") is None
    assert taxonomy.normalise("  ") is None


def test_taxonomy_returns_copies_of_parents_and_names():
    taxonomy = SeededTaxonomy(get_settings())

    parents = taxonomy.parents("fastapi")
    parents.append("mutated")

    assert taxonomy.parents("fastapi") == ["python", "backend"]
    assert taxonomy.name("fastapi") == "FastAPI"
    with pytest.raises(KeyError):
        taxonomy.name("missing")


def test_taxonomy_rejects_ambiguous_terms(tmp_path: Path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "skills.yaml").write_text(
        """
skills:
  - {id: one, name: One, parents: [], aliases: [shared]}
  - {id: two, name: Two, parents: [], aliases: [Shared]}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Ambiguous skill term"):
        SeededTaxonomy(Settings(knowledge_data_dir=knowledge_dir))


def _market_row(skill_id: str, frequency: float | None, role: str = "backend") -> dict:
    return {
        "skill_id": skill_id,
        "frequency": frequency,
        "role": role,
        "region": "AU",
        "provenance": {
            "source_kind": "seeded",
            "source_name": "test demand table",
            "confidence": 0.6,
            "sample_size": 20,
            "collected_at": "2026-09-01",
        },
    }


def test_seeded_demand_finds_and_ranks_market_skills(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rows = [
        _market_row("unknown", None),
        _market_row("python", 0.62),
        _market_row("sql", 0.58),
        _market_row("react", 0.9, role="frontend"),
    ]
    (data_dir / "market.json").write_text(json.dumps(rows), encoding="utf-8")
    demand = SeededDemand(Settings(data_dir=data_dir))

    hit = demand.frequency("python", "BACKEND", "au")

    assert hit is not None
    assert hit.frequency == 0.62
    assert demand.frequency("react", "backend", "AU") is None
    assert [skill.skill_id for skill in demand.top_skills("backend", "AU", 3)] == [
        "python",
        "sql",
        "unknown",
    ]
    assert demand.top_skills("backend", "AU", 0) == []


def test_seeded_demand_degrades_when_the_data_file_is_absent(tmp_path: Path):
    demand = SeededDemand(Settings(data_dir=tmp_path / "missing"))

    assert demand.frequency("python", "backend", "AU") is None
    assert demand.top_skills("backend", "AU", 10) == []
