"""The forward-looking concept graph behind the roadmap diagram."""

from app.config import Settings
from app.schemas.common import Provenance, SourceKind
from app.schemas.market import MarketSkill
from app.schemas.roadmap import NodeStatus
from app.schemas.scores import SkillStatus
from app.services.knowledge.taxonomy.seeded import SeededTaxonomy
from app.services.roadmap.concepts import build_graph

TAXONOMY = SeededTaxonomy(Settings())
EVIDENCE = [{"file": "orders/service.py", "lines": [40, 58], "commit": "abc1234"}]


def _market(skill_id: str, frequency: float | None = 0.5) -> MarketSkill:
    return MarketSkill(
        skill_id=skill_id,
        frequency=frequency,
        role="software_engineer",
        region="AU",
        provenance=Provenance(
            source_kind=SourceKind.SEEDED,
            source_name="seeded demand table v1",
            confidence=0.6,
            sample_size=400,
        ),
    )


def _status(skill_id: str, tier: str) -> SkillStatus:
    return SkillStatus.model_validate(
        {"skill_id": skill_id, "tier": tier, "evidence": EVIDENCE}
    )


def _graph(skills, demand):
    return build_graph(skills, demand, "software_engineer", "AU", TAXONOMY)


def _find(graph, skill_id):
    for concept in graph.concepts:
        for skill in concept.skills:
            if skill.skill_id == skill_id:
                return concept, skill
    raise AssertionError(f"{skill_id} is missing from the graph")


def test_skills_group_under_their_nearest_taxonomy_root():
    graph = _graph(
        [_status("fastapi", "verified"), _status("react", "verified")],
        {"fastapi": _market("fastapi"), "react": _market("react")},
    )

    assert _find(graph, "fastapi")[0].concept_id == "backend"
    assert _find(graph, "react")[0].concept_id == "frontend"


def test_verified_skill_is_pointed_past_the_basics():
    graph = _graph([_status("python", "verified")], {"python": _market("python")})

    _, skill = _find(graph, "python")
    assert skill.status is NodeStatus.VERIFIED
    assert skill.evidence[0].file == "orders/service.py"
    assert "orders/service.py" in skill.focus


def test_touched_skill_is_familiar_and_still_points_forward():
    graph = _graph([_status("java", "touched")], {"java": _market("java")})

    _, skill = _find(graph, "java")
    assert skill.status is NodeStatus.FAMILIAR
    assert "basics" in skill.focus.casefold()


def test_new_skill_names_the_work_it_builds_on():
    graph = _graph(
        [_status("python", "verified")],
        {"python": _market("python"), "django": _market("django")},
    )

    _, skill = _find(graph, "django")
    assert skill.status is NodeStatus.NEW
    assert "Python" in skill.related_to
    assert "Python" in skill.focus


def test_unrelated_new_skill_starts_from_fundamentals():
    graph = _graph(
        [_status("python", "verified")],
        {"python": _market("python"), "flutter": _market("flutter")},
    )

    _, skill = _find(graph, "flutter")
    assert skill.related_to == []
    assert "fundamentals" in skill.focus.casefold()


def test_missing_market_frequency_never_drops_a_skill():
    graph = _graph(
        [_status("python", "verified")],
        {"python": _market("python", None), "django": _market("django", None)},
    )

    _, python = _find(graph, "python")
    _, django = _find(graph, "django")
    assert python.market_frequency is None
    assert django.market_frequency is None
    assert "%" not in python.focus


def test_concepts_carry_counts_and_lead_with_the_highest_priority():
    graph = _graph(
        [_status("python", "verified"), _status("java", "touched")],
        {
            "python": _market("python", 0.9),
            "java": _market("java", 0.2),
            "django": _market("django", 0.1),
        },
    )

    priorities = [concept.priority for concept in graph.concepts]
    assert priorities == sorted(priorities, reverse=True)
    languages = next(c for c in graph.concepts if c.concept_id == "programming_languages")
    assert languages.verified_count == 1
    assert languages.familiar_count == 1
    assert languages.summary


def test_graph_endpoint_serves_concepts_from_the_mock_roadmap(monkeypatch):
    from app.routers import roadmap as roadmap_router

    monkeypatch.setattr(roadmap_router, "get_settings", lambda: Settings(mock_mode=True))

    graph = roadmap_router.portfolio_roadmap_graph("demo-user", None, "software_engineer", "AU")

    assert graph.role == "software_engineer"
    assert graph.concepts
    assert all(concept.summary for concept in graph.concepts)
    assert all(skill.focus for concept in graph.concepts for skill in concept.skills)


def test_graph_endpoint_survives_a_role_the_fixture_does_not_have(monkeypatch):
    from app.routers import roadmap as roadmap_router

    monkeypatch.setattr(roadmap_router, "get_settings", lambda: Settings(mock_mode=True))

    graph = roadmap_router.portfolio_roadmap_graph("demo-user", None, "astronaut", "AU")

    assert graph.concepts
