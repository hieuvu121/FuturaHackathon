"""Integrity checks for the seeded knowledge contracts."""

import yaml

from app.config import get_settings


def _load(name: str):
    path = get_settings().knowledge_data_dir / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_skill_catalogue_is_complete_and_connected():
    skills = _load("skills")["skills"]
    ids = [skill["id"] for skill in skills]

    assert 80 <= len(skills) <= 120
    assert len(ids) == len(set(ids))
    assert all(parent in set(ids) for skill in skills for parent in skill["parents"])


def test_skill_lookup_terms_are_unambiguous():
    skills = _load("skills")["skills"]
    owners: dict[str, str] = {}

    for skill in skills:
        terms = [skill["id"], skill["name"], *skill["aliases"]]
        for term in terms:
            key = term.casefold().strip()
            assert key not in owners or owners[key] == skill["id"], (
                f"{term!r} maps to both {owners[key]!r} and {skill['id']!r}"
            )
            owners[key] = skill["id"]


def test_every_dimension_has_four_levels_and_thresholds():
    dimensions = _load("dimensions")["dimensions"]

    assert len(dimensions) == 6
    assert all(set(dimension["levels"]) == {1, 2, 3, 4} for dimension in dimensions)
    assert all(dimension["metric_thresholds"] for dimension in dimensions)
