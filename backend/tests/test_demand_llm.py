"""The LLM demand provider: always labelled an estimate, never able to break the roadmap."""

from datetime import date
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.db import Base, Repo, SkillStatusRow, User
from app.routers import roadmap as roadmap_router
from app.schemas.common import SourceKind
from app.services.knowledge import get_demand
from app.services.knowledge.demand import llm
from app.services.knowledge.demand.llm import (
    MAX_CONFIDENCE,
    DemandEstimateError,
    EstimateBatch,
    LLMDemand,
)


def _settings(tmp_path, **overrides) -> Settings:
    return Settings(
        mock_mode=False,
        demand_source="llm",
        llm_provider="openai",
        openai_api_key="test-key",
        cache_dir=tmp_path / "cache",
        **overrides,
    )


def _batch(*rows: tuple[str, float | None, float | None]) -> EstimateBatch:
    return EstimateBatch.model_validate(
        {
            "skills": [
                {"skill_id": skill_id, "frequency": frequency, "confidence": confidence}
                for skill_id, frequency, confidence in rows
            ]
        }
    )


def _stub_model(monkeypatch, batch: EstimateBatch) -> list[str]:
    prompts: list[str] = []

    def fake(settings, prompt):
        prompts.append(prompt)
        return batch

    monkeypatch.setattr(llm, "_request_estimates", fake)
    return prompts


def test_rows_are_stamped_as_clamped_estimates(monkeypatch, tmp_path):
    prompts = _stub_model(monkeypatch, _batch(("docker", 0.5, 0.95), ("go", 0.2, 0.1)))

    rows = LLMDemand(_settings(tmp_path)).top_skills(" Backend ", "AU", limit=10)

    assert [row.skill_id for row in rows] == ["docker", "go"]
    for row in rows:
        assert row.role == "Backend"
        assert row.region == "AU"
        assert row.provenance.source_kind == SourceKind.ESTIMATED
        assert row.provenance.sample_size is None
        assert row.provenance.collected_at == date.today()
        assert row.provenance.confidence <= MAX_CONFIDENCE
        assert "gpt-5" in row.provenance.source_name
    assert rows[0].provenance.confidence == MAX_CONFIDENCE
    assert rows[1].provenance.confidence == 0.1
    assert "- docker: " in prompts[0]
    assert "Backend role in AU" in prompts[0]


def test_aliases_become_canonical_ids_and_unknown_skills_are_dropped(monkeypatch, tmp_path):
    _stub_model(
        monkeypatch,
        _batch(("golang", 0.3, 0.3), ("go", 0.9, 0.3), ("quantum_basket_weaving", 0.8, 0.4)),
    )

    rows = LLMDemand(_settings(tmp_path)).top_skills("backend", "AU", limit=10)

    assert [(row.skill_id, row.frequency) for row in rows] == [("go", 0.3)]


def test_unknown_or_impossible_frequency_stays_null_and_sorts_last(monkeypatch, tmp_path):
    _stub_model(
        monkeypatch,
        _batch(("rust", None, 0.4), ("docker", 0.6, 0.4), ("go", 1.7, 0.4), ("python", 0.8, 0.4)),
    )
    demand = LLMDemand(_settings(tmp_path))

    rows = demand.top_skills("backend", "AU", limit=10)

    assert [(row.skill_id, row.frequency) for row in rows] == [
        ("python", 0.8),
        ("docker", 0.6),
        ("go", None),
        ("rust", None),
    ]
    assert rows[-1].provenance.confidence == 0.0
    assert [row.skill_id for row in demand.top_skills("backend", "AU", limit=1)] == ["python"]
    assert demand.top_skills("backend", "AU", limit=0) == []


def test_frequency_reads_the_same_estimate_and_returns_none_when_absent(monkeypatch, tmp_path):
    prompts = _stub_model(monkeypatch, _batch(("docker", 0.6, 0.4)))
    demand = LLMDemand(_settings(tmp_path))

    assert demand.frequency("docker", "backend", "AU").frequency == 0.6
    assert demand.frequency("rust", "backend", "AU") is None
    assert len(prompts) == 1


def test_cached_estimate_survives_a_new_instance_without_calling_the_model(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    prompts = _stub_model(monkeypatch, _batch(("docker", 0.6, 0.4), ("go", 0.3, 0.4)))
    first = LLMDemand(settings).top_skills("backend", "AU", limit=10)

    def explode(settings, prompt):
        raise AssertionError("a cached estimate must not call the model again")

    monkeypatch.setattr(llm, "_request_estimates", explode)
    second = LLMDemand(settings).top_skills("Backend", "au", limit=10)

    assert len(prompts) == 1
    assert second == first
    assert list((settings.cache_dir / "demand_llm").glob("*.json"))


def test_edited_cache_cannot_relabel_an_estimate(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    _stub_model(monkeypatch, _batch(("docker", 0.6, 0.4)))
    LLMDemand(settings).top_skills("backend", "AU", limit=10)
    path = next((settings.cache_dir / "demand_llm").glob("*.json"))
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["provenance"].update({"source_kind": "scraped", "confidence": 0.99, "sample_size": 5000})
    path.write_text(json.dumps(rows), encoding="utf-8")

    row = LLMDemand(settings).frequency("docker", "backend", "AU")

    assert row.provenance.source_kind == SourceKind.ESTIMATED
    assert row.provenance.confidence == MAX_CONFIDENCE
    assert row.provenance.sample_size is None


def test_provider_failure_degrades_and_is_not_cached(monkeypatch, tmp_path):
    settings = _settings(tmp_path)

    def fail(settings, prompt):
        raise ConnectionError("provider down")

    monkeypatch.setattr(llm, "_request_estimates", fail)
    demand = LLMDemand(settings)

    assert demand.top_skills("backend", "AU", limit=10) == []
    assert demand.frequency("docker", "backend", "AU") is None
    assert not list((settings.cache_dir / "demand_llm").glob("*.json"))

    _stub_model(monkeypatch, _batch(("docker", 0.6, 0.4)))
    assert [row.skill_id for row in demand.top_skills("backend", "AU", limit=10)] == ["docker"]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_missing_credentials_degrade_without_a_network_call(tmp_path, provider):
    settings = _settings(tmp_path, anthropic_api_key="").model_copy(
        update={"llm_provider": provider, "openai_api_key": ""}
    )
    demand = LLMDemand(settings)

    assert demand.top_skills("backend", "AU", limit=10) == []
    assert demand.frequency("docker", "backend", "AU") is None


def test_openai_response_without_parsed_output_degrades(monkeypatch, tmp_path):
    class Responses:
        def parse(self, **kwargs):
            return type("Response", (), {"output_parsed": None})()

    class Client:
        def __init__(self, **kwargs):
            self.responses = Responses()

    monkeypatch.setattr(llm, "OpenAI", Client)

    assert LLMDemand(_settings(tmp_path)).top_skills("backend", "AU", limit=10) == []


def test_malformed_anthropic_text_degrades(monkeypatch, tmp_path):
    class Messages:
        def create(self, **kwargs):
            block = type("Block", (), {"type": "text", "text": "Docker is popular, roughly 60%."})()
            return type("Response", (), {"content": [block]})()

    class Client:
        def __init__(self, **kwargs):
            self.messages = Messages()

    monkeypatch.setattr(llm.anthropic, "Anthropic", Client)
    settings = _settings(tmp_path, anthropic_api_key="test-key").model_copy(
        update={"llm_provider": "anthropic"}
    )

    assert LLMDemand(settings).top_skills("backend", "AU", limit=10) == []


def test_parse_batch_accepts_fenced_json_and_rejects_invalid_shapes():
    fenced = '```json\n{"skills":[{"skill_id":"go","frequency":null,"confidence":null}]}\n```'
    assert llm._parse_batch(fenced).skills[0].frequency is None

    for bad in ("not json", '{"skills":[{"skill_id":"go","frequency":"often","confidence":0.1}]}'):
        with pytest.raises(DemandEstimateError):
            llm._parse_batch(bad)


def test_demand_source_llm_selects_this_provider(tmp_path):
    assert isinstance(get_demand(_settings(tmp_path)), LLMDemand)


def _repo_with_touched_python(db: Session) -> None:
    db.add(User(id=1, github_login="developer"))
    db.add(Repo(id=10, user_id=1, full_name="owner/project"))
    db.add(
        SkillStatusRow(
            user_id=1,
            repo_id=10,
            skill_id="python",
            tier="touched",
            evidence=[{"file": "app.py", "lines": [1, 2], "commit": "abc"}],
        )
    )
    db.commit()


def test_roadmap_api_labels_llm_learn_new_as_estimated(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = _settings(tmp_path)
    monkeypatch.setattr(roadmap_router, "get_settings", lambda: settings)
    _stub_model(
        monkeypatch, _batch(("python", 0.7, 0.4), ("docker", 0.6, 0.4), ("rust", None, None))
    )
    with Session(engine) as db:
        _repo_with_touched_python(db)

        first = roadmap_router.roadmap("10", "developer", db)
        second = roadmap_router.roadmap("10", "developer", db)

    assert [item.skill_id for item in first.revise] == ["python"]
    assert first.revise[0].evidence[0].file == "app.py"
    assert {item.skill_id for item in first.learn_new} == {"docker", "rust"}
    for item in first.learn_new:
        assert item.provenance.source_kind == SourceKind.ESTIMATED
        assert item.provenance.confidence <= MAX_CONFIDENCE
        assert item.provenance.sample_size is None
        assert "estimated provisional" in item.reason.casefold()
    rust = next(item for item in first.learn_new if item.skill_id == "rust")
    assert rust.market_frequency is None
    assert rust.priority > 0
    assert second == first


def test_roadmap_api_keeps_evidence_buckets_when_the_provider_fails(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = _settings(tmp_path)
    monkeypatch.setattr(roadmap_router, "get_settings", lambda: settings)

    def fail(settings, prompt):
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(llm, "_request_estimates", fail)
    with Session(engine) as db:
        _repo_with_touched_python(db)

        result = roadmap_router.roadmap("10", "developer", db)

    assert [item.skill_id for item in result.revise] == ["python"]
    assert result.learn_new == []
