"""Every mock fixture must validate against its schema.

This is the guard that keeps the mock-mode demo honest: if Track D edits a
fixture into a shape the frontend cannot consume, this fails before the demo does.
"""

import json

import pytest

from app.config import get_settings
from app.schemas.findings import Finding
from app.schemas.market import MarketSkill
from app.schemas.recall import Question
from app.schemas.repo_map import RepoMap
from app.schemas.roadmap import Buckets
from app.schemas.scores import Scores

MOCK = get_settings().mock_dir


def _load(name: str):
    return json.loads((MOCK / f"{name}.json").read_text())


def test_repo_map_fixture():
    RepoMap.model_validate(_load("repo_map"))


def test_findings_fixture():
    findings = [Finding.model_validate(f) for f in _load("findings")]
    assert findings, "findings fixture must not be empty"
    assert all(f.evidence.file for f in findings), "every finding carries Evidence"


def test_scores_fixture():
    scores = Scores.model_validate(_load("scores"))
    assert len(scores.dimensions) == 6, "six dimensions, per dimensions.yaml"


def test_questions_fixture():
    questions = [Question.model_validate(q) for q in _load("questions")]
    assert {q.type.value for q in questions} == {"recall", "justify", "transfer", "debug", "extend"}


def test_market_fixture_allows_null_frequency():
    skills = [MarketSkill.model_validate(s) for s in _load("market")]
    assert any(s.frequency is None for s in skills), (
        "keep at least one null frequency: the roadmap must degrade, not crash"
    )


def test_roadmap_fixture():
    Buckets.model_validate(_load("roadmap"))


@pytest.mark.parametrize("dimension_id", [
    "code_structure", "testing", "error_handling",
    "domain_modelling", "version_control", "security_awareness",
])
def test_scores_cover_every_dimension(dimension_id):
    scores = Scores.model_validate(_load("scores"))
    assert dimension_id in {d.dimension for d in scores.dimensions}


def test_demand_chain_degrades_to_none():
    """The roadmap's source of truth is undecided (plan.md §10).

    Whatever it turns out to be, a chain that answers nothing must return None
    rather than raise -- that is invariant #5, and it is what lets every other
    track keep working while the decision is open.
    """
    from app.services.knowledge.demand.chained import ChainedDemand

    class Silent:
        def frequency(self, skill_id, role, region):
            return None

    chain = ChainedDemand(get_settings(), [Silent(), Silent()])
    assert chain.frequency("docker", "backend", "AU") is None


def test_demand_chain_takes_first_answer_and_keeps_its_provenance():
    from app.services.knowledge.demand.chained import ChainedDemand

    class Silent:
        def frequency(self, skill_id, role, region):
            return None

    class Estimating:
        def frequency(self, skill_id, role, region):
            return MarketSkill.model_validate({
                "skill_id": skill_id, "frequency": 0.3, "role": role, "region": region,
                "provenance": {
                    "source_kind": "estimated", "source_name": "LLM estimate (test)",
                    "confidence": 0.4, "sample_size": None, "collected_at": None,
                },
            })

    chain = ChainedDemand(get_settings(), [Silent(), Estimating(), Silent()])
    hit = chain.frequency("docker", "backend", "AU")
    assert hit is not None
    assert hit.provenance.source_kind.value == "estimated", "a guess must stay labelled a guess"
