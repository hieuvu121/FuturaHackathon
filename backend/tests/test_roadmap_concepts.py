"""The forward-looking concept graph behind the roadmap diagram."""

from app.config import Settings
from app.schemas.common import Provenance, SourceKind
from app.schemas.findings import Finding
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


def _graph(skills, demand, findings=None):
    return build_graph(skills, demand, "software_engineer", "AU", TAXONOMY, findings or [])


def _finding(dimension: str, observation: str, file: str = "orders/repo.py") -> Finding:
    return Finding.model_validate(
        {
            "id": f"f-{dimension}",
            "dimension": dimension,
            "severity": "high",
            "observation": observation,
            "evidence": {"file": file, "lines": [44, 52], "commit": "abc1234"},
            "confidence": 0.8,
        }
    )


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
    assert "service.py:40" in skill.focus
    assert "orders/" not in skill.focus


def test_touched_skill_is_familiar_and_still_points_forward():
    graph = _graph([_status("java", "touched")], {"java": _market("java")})

    _, skill = _find(graph, "java")
    assert skill.status is NodeStatus.FAMILIAR
    # Forward-looking, not a "go back and revise" instruction.
    assert "prove it" in skill.focus.casefold()
    assert "revise" not in skill.focus.casefold()


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


def test_mastery_tracks_the_evidence_tier():
    graph = _graph(
        [_status("python", "verified"), _status("java", "touched")],
        {"python": _market("python"), "java": _market("java"), "flutter": _market("flutter")},
    )

    assert _find(graph, "python")[1].mastery == 1.0
    assert _find(graph, "java")[1].mastery == 0.5
    assert _find(graph, "flutter")[1].mastery == 0.0


def test_concept_mastery_is_the_mean_of_its_skills():
    graph = _graph(
        [_status("python", "verified"), _status("java", "touched")],
        {"python": _market("python"), "java": _market("java"), "go": _market("go")},
    )

    languages = next(c for c in graph.concepts if c.concept_id == "programming_languages")
    # verified 1.0 + familiar 0.5 + new 0.0 over three skills
    assert languages.mastery == round((1.0 + 0.5 + 0.0) / 3, 4)


def test_focus_names_the_real_problem_when_a_finding_matches():
    graph = _graph(
        [_status("data_modelling", "touched")],
        {"data_modelling": _market("data_modelling")},
        [_finding("domain_modelling", "Orders are fetched one row at a time, causing N+1 queries.")],
    )

    _, skill = _find(graph, "data_modelling")
    assert "repo.py:44" in skill.focus
    assert "N+1" in skill.focus
    assert skill.gap_evidence is not None
    assert skill.gap_evidence.file == "orders/repo.py"


def test_a_new_skill_is_justified_by_a_gap_in_related_code():
    """The postgres/N+1 case: an untouched skill that answers a real problem."""
    graph = _graph(
        [_status("data_modelling", "touched")],
        {"data_modelling": _market("data_modelling"), "postgresql": _market("postgresql")},
        [_finding("domain_modelling", "Orders are fetched one row at a time, causing N+1 queries.")],
    )

    _, skill = _find(graph, "postgresql")
    assert skill.status is NodeStatus.NEW
    assert "N+1" in skill.focus
    assert skill.gap_evidence is not None


def test_focus_stays_short_and_drops_the_market_sentence():
    graph = _graph(
        [_status("python", "verified")],
        {"python": _market("python", 0.58), "django": _market("django", 0.41)},
    )

    for concept in graph.concepts:
        for skill in concept.skills:
            assert len(skill.focus) <= 160, skill.focus
            # the percentage belongs to the bar, not the prose
            assert "sampled" not in skill.focus
            assert "%" not in skill.focus


def test_a_skill_with_no_matching_finding_still_gets_a_next_step():
    graph = _graph(
        [_status("python", "verified")],
        {"python": _market("python")},
        [_finding("security_awareness", "Secrets are read from a plaintext file.")],
    )

    _, skill = _find(graph, "python")
    assert skill.focus
    assert skill.gap_evidence is None


def test_one_concept_never_prints_the_same_finding_twice():
    """A dimension has many findings; dealing them out keeps each node distinct."""
    findings = [
        _finding("domain_modelling", "Orders are fetched one row at a time, causing N+1 queries.", "a.py"),
        _finding("domain_modelling", "Customer ids are stored as free text.", "b.py"),
        _finding("domain_modelling", "Money is held as a float.", "c.py"),
    ]
    for index, finding in enumerate(findings):
        finding.id = f"f{index}"

    graph = _graph(
        [_status("data_modelling", "touched")],
        {
            "data_modelling": _market("data_modelling"),
            "sql": _market("sql"),
            "postgresql": _market("postgresql"),
        },
        findings,
    )

    data = next(c for c in graph.concepts if c.concept_id == "data")
    cited = [s.gap_evidence.file for s in data.skills if s.gap_evidence]
    assert len(cited) == len(set(cited)), cited


def test_a_compressed_finding_never_ends_mid_word():
    long_observation = (
        "IndexedFile hash lookup is scoped only by file_path and ignores the "
        "repository it belongs to, so two repos collide."
    )
    graph = _graph(
        [_status("data_modelling", "touched")],
        {"data_modelling": _market("data_modelling")},
        [_finding("domain_modelling", long_observation)],
    )

    _, skill = _find(graph, "data_modelling")
    problem = skill.focus.split(": ", 1)[1].rsplit(". ", 1)[0]
    assert problem.endswith("...") or problem in long_observation, problem
    if problem.endswith("..."):
        assert long_observation.startswith(problem[:-3])
