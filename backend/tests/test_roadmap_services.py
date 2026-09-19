"""Evidence-first roadmap matching and bucket behavior."""

from datetime import date

from app.config import Settings
from app.schemas.common import Evidence, Provenance, SourceKind
from app.schemas.market import MarketSkill
from app.schemas.scores import SkillStatus, Tier
from app.services.knowledge.demand.seeded import SeededDemand
from app.services.knowledge.taxonomy.seeded import SeededTaxonomy
from app.services.roadmap.buckets import build
from app.services.roadmap.matcher import match


class FakeTaxonomy:
    aliases = {
        "py": "python",
        "python": "python",
        "unit testing": "testing_unit",
        "testing_unit": "testing_unit",
        "clean_code": "clean_code",
        "docker": "docker",
        "async_programming": "async_programming",
    }
    names = {
        "python": "Python",
        "testing_unit": "Unit Testing",
        "clean_code": "Clean Code",
        "docker": "Docker",
        "async_programming": "Asynchronous Programming",
    }
    parent_map = {
        "python": ["programming_languages"],
        "testing_unit": ["testing"],
        "clean_code": ["programming_concepts"],
        "docker": ["devops"],
        "async_programming": ["programming_concepts"],
    }

    def normalise(self, raw):
        return self.aliases.get(raw.casefold().strip())

    def parents(self, skill_id):
        return list(self.parent_map.get(skill_id, []))

    def name(self, skill_id):
        return self.names[skill_id]


def _provenance(confidence: float = 0.6) -> Provenance:
    return Provenance(
        source_kind=SourceKind.SEEDED,
        source_name="test seeded demand",
        confidence=confidence,
        sample_size=20,
        collected_at=date(2026, 9, 1),
    )


def _market(skill_id: str, frequency: float | None) -> MarketSkill:
    return MarketSkill(
        skill_id=skill_id,
        frequency=frequency,
        role="backend",
        region="AU",
        provenance=_provenance(0.3 if frequency is None else 0.6),
    )


def _status(skill_id: str, tier: Tier, line: int = 1) -> SkillStatus:
    return SkillStatus(
        skill_id=skill_id,
        tier=tier,
        evidence=[Evidence(file="app.py", lines=(line, line + 1), commit="abc")],
    )


class FakeDemand:
    def __init__(self):
        self.rows = {
            "python": _market("python", 0.62),
            "testing_unit": _market("testing_unit", 0.41),
            "clean_code": _market("clean_code", None),
            "docker": _market("docker", 0.47),
            "async_programming": _market("async_programming", None),
        }

    def frequency(self, skill_id, role, region):
        return self.rows.get(skill_id)

    def top_skills(self, role, region, limit):
        return [self.rows["docker"], self.rows["async_programming"]][:limit]


class UnavailableDemand:
    def frequency(self, skill_id, role, region):
        raise NotImplementedError

    def top_skills(self, role, region, limit):
        raise NotImplementedError


def test_match_normalises_known_skills_and_adds_unseen_demand_candidates():
    skills = [_status("py", Tier.TOUCHED), _status("python", Tier.VERIFIED, 3)]

    matched = match(skills, FakeTaxonomy(), FakeDemand(), "backend", "AU")

    assert list(matched) == ["python", "docker", "async_programming"]
    assert matched["python"].frequency == 0.62


def test_verified_overrides_touched_and_evidence_is_merged():
    skills = [
        _status("python", Tier.TOUCHED, 1),
        _status("py", Tier.VERIFIED, 5),
        _status("testing_unit", Tier.TOUCHED, 10),
    ]
    demand = match(skills, FakeTaxonomy(), FakeDemand(), "backend", "AU")

    roadmap = build(skills, demand, "backend", "AU", FakeTaxonomy())

    assert [item.skill_id for item in roadmap.deepen] == ["python"]
    assert [item.skill_id for item in roadmap.revise] == ["testing_unit"]
    assert len(roadmap.deepen[0].evidence) == 2


def test_learn_new_excludes_known_skills_and_preserves_provenance():
    skills = [_status("python", Tier.TOUCHED)]
    demand = match(skills, FakeTaxonomy(), FakeDemand(), "backend", "AU")

    roadmap = build(skills, demand, "backend", "AU", FakeTaxonomy())

    assert {item.skill_id for item in roadmap.learn_new} == {"docker", "async_programming"}
    docker = next(item for item in roadmap.learn_new if item.skill_id == "docker")
    assert docker.market_frequency == 0.47
    assert docker.provenance == _provenance()
    assert "provisional" in docker.reason.casefold()


def test_null_frequency_ranks_by_taxonomy_proximity_instead_of_dropping():
    skills = [_status("clean_code", Tier.TOUCHED)]
    demand = match(skills, FakeTaxonomy(), FakeDemand(), "backend", "AU")

    roadmap = build(skills, demand, "backend", "AU", FakeTaxonomy())

    assert [item.skill_id for item in roadmap.learn_new][:2] == [
        "async_programming",
        "docker",
    ]
    async_item = roadmap.learn_new[0]
    assert async_item.market_frequency is None
    assert async_item.priority > 0
    assert "frequency is unavailable" in async_item.reason.casefold()


def test_unavailable_demand_still_returns_evidence_buckets():
    skills = [
        _status("python", Tier.VERIFIED),
        _status("testing_unit", Tier.TOUCHED),
    ]

    demand = match(skills, FakeTaxonomy(), UnavailableDemand(), "backend", "AU")
    roadmap = build(skills, demand, "backend", "AU", FakeTaxonomy())

    assert [item.skill_id for item in roadmap.deepen] == ["python"]
    assert [item.skill_id for item in roadmap.revise] == ["testing_unit"]
    assert roadmap.learn_new == []


def test_real_seeded_taxonomy_and_demand_build_all_three_buckets():
    settings = Settings(demand_source="seeded")
    taxonomy = SeededTaxonomy(settings)
    demand_source = SeededDemand(settings)
    skills = [
        _status("py", Tier.VERIFIED),
        _status("unit testing", Tier.TOUCHED),
    ]

    demand = match(skills, taxonomy, demand_source, "backend", "AU")
    roadmap = build(skills, demand, "backend", "AU", taxonomy)

    assert [item.skill_id for item in roadmap.deepen] == ["python"]
    assert [item.skill_id for item in roadmap.revise] == ["testing_unit"]
    assert "docker" in {item.skill_id for item in roadmap.learn_new}
    async_item = next(item for item in roadmap.learn_new if item.skill_id == "async_programming")
    assert async_item.market_frequency is None
    assert async_item.provenance.source_kind == SourceKind.SEEDED
