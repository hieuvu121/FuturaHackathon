"""Seeded competency ladder provider tests."""

from app.config import get_settings
from app.services.knowledge.ladder.seeded import SeededLadder


def test_seeded_ladder_loads_dimensions_levels_and_thresholds():
    ladder = SeededLadder(get_settings())

    assert ladder.dimensions() == [
        "code_structure",
        "testing",
        "error_handling",
        "domain_modelling",
        "version_control",
        "security_awareness",
    ]
    assert set(ladder.levels("testing")) == {1, 2, 3, 4}
    assert ladder.metric_thresholds("testing")["test_coverage_ratio"][4] == ">0.6"


def test_seeded_ladder_maps_seniority_to_target_level():
    ladder = SeededLadder(get_settings())

    assert ladder.target_level("testing", "backend", "junior") == 2
    assert ladder.target_level("testing", "backend", "mid-level") == 3
    assert ladder.target_level("testing", "backend", "senior") == 4
