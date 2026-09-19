"""LLM-estimated demand. Owner: Roadmap Demand Backend.

The provisional demo input for the roadmap's Learn New bucket (plan.md §10.1).
The model is asked how often each taxonomy skill appears in job ads for a role
and region. It sees the role, the region, and the skill vocabulary -- never the
user's repository. Revise and Deepen stay evidence-first and never read this.

This is a GUESS and must be labelled as one: every row comes back with
source_kind=ESTIMATED, confidence <= 0.4, and sample_size=None, so SourceBadge
renders it visibly weaker than a scraped figure. Never present an estimate as
measurement -- the whole product is an argument against unevidenced claims.

One model call estimates the whole vocabulary for a (role, region) pair. The
result is cached under cache_dir/demand_llm/ so the roadmap neither re-calls the
model nor reorders itself mid-demo. Delete the file to force a fresh estimate.

Returning None / [] is always acceptable. The roadmap degrades by design, so
this provider fails soft: missing credentials, provider errors, and malformed
output are logged and never raised into the roadmap endpoint.
"""

from datetime import date
import json
import logging
import math
from pathlib import Path
import re

import anthropic
from openai import OpenAI
from pydantic import BaseModel, ValidationError
import yaml

from ....config import Settings
from ....schemas.common import Provenance, SourceKind
from ....schemas.market import MarketSkill
from ..base import SkillTaxonomy, get_taxonomy

logger = logging.getLogger(__name__)

MAX_CONFIDENCE = 0.4
REQUEST_TIMEOUT_SECONDS = 60
MAX_LABEL_CHARS = 60

ESTIMATE_PROMPT = """Estimate how frequently each skill below is named as a requirement
in job advertisements for a {role} role in {region}.

For every skill you can reasonably judge, return its id exactly as written, a
frequency between 0 and 1 (the share of such ads naming it), and your confidence
between 0 and 1. Set frequency to null when you have no defensible numerical
basis -- prefer null over a confident guess. Omit skills irrelevant to the role,
and prefer specific skills over broad categories. Never invent ids that are not
in the list. These are estimates, not measurements; do not claim a sample size.

Skills (id: name):
{vocabulary}
"""

JSON_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class DemandEstimateError(RuntimeError):
    """Raised when a model response cannot become typed estimates."""


class SkillEstimate(BaseModel):
    skill_id: str
    frequency: float | None
    confidence: float | None


class EstimateBatch(BaseModel):
    """Object wrapper required by OpenAI structured outputs."""

    skills: list[SkillEstimate]


def estimated_provenance(
    model: str, confidence: float | None = None, collected_at: date | None = None
) -> Provenance:
    claimed = MAX_CONFIDENCE if confidence is None or math.isnan(confidence) else confidence
    return Provenance(
        source_kind=SourceKind.ESTIMATED,
        source_name=f"LLM estimate ({model})",
        confidence=max(0.0, min(claimed, MAX_CONFIDENCE)),
        sample_size=None,
        collected_at=collected_at,
    )


def _model_name(settings: Settings) -> str:
    if settings.llm_provider == "openai" and settings.generator_model.casefold().startswith("claude"):
        return settings.scanner_model
    return settings.generator_model


def _parse_batch(response_text: str) -> EstimateBatch:
    fence = JSON_FENCE.match(response_text.strip())
    payload_text = fence.group(1) if fence else response_text
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise DemandEstimateError("Model response was not valid JSON") from exc
    if isinstance(payload, list):
        payload = {"skills": payload}
    try:
        return EstimateBatch.model_validate(payload)
    except ValidationError as exc:
        raise DemandEstimateError("Model response contained an invalid estimate") from exc


def _request_estimates(settings: Settings, prompt: str) -> EstimateBatch:
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        response = OpenAI(
            api_key=settings.openai_api_key, timeout=REQUEST_TIMEOUT_SECONDS
        ).responses.parse(
            model=_model_name(settings),
            input=[{"role": "user", "content": prompt}],
            text_format=EstimateBatch,
        )
        if response.output_parsed is None:
            raise DemandEstimateError("Model returned no structured estimates")
        return response.output_parsed
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    response = anthropic.Anthropic(
        api_key=settings.anthropic_api_key, timeout=REQUEST_TIMEOUT_SECONDS
    ).messages.create(
        model=_model_name(settings),
        max_tokens=4_000,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": prompt
                + '\nReturn ONLY JSON: {"skills":[{"skill_id":"...","frequency":0.0,"confidence":0.0}]}',
            }
        ],
    )
    text = "\n".join(block.text for block in response.content if block.type == "text")
    return _parse_batch(text)


def _label(value: str) -> str:
    """Role and region arrive from the query string; keep them short and single-line."""
    return " ".join(value.split())[:MAX_LABEL_CHARS]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "any"


def _usable_frequency(value: float | None) -> float | None:
    """Unknown stays unknown. An out-of-range number is garbage, not a percentage."""
    if value is None or math.isnan(value) or not 0.0 <= value <= 1.0:
        return None
    return value


def _ordering(skill: MarketSkill) -> tuple[bool, float, str]:
    return (skill.frequency is None, -(skill.frequency or 0.0), skill.skill_id)


class LLMDemand:
    def __init__(self, settings: Settings, taxonomy: SkillTaxonomy | None = None) -> None:
        self.settings = settings
        self.cache_dir = settings.cache_dir / "demand_llm"
        self._taxonomy = taxonomy
        self._estimates: dict[tuple[str, str], dict[str, MarketSkill]] = {}

    def frequency(self, skill_id: str, role: str, region: str) -> MarketSkill | None:
        """Return None on UNKNOWN. Do not coerce an unknown into a number."""
        return self._load(role, region).get(skill_id)

    def top_skills(self, role: str, region: str, limit: int) -> list[MarketSkill]:
        if limit <= 0:
            return []
        return sorted(self._load(role, region).values(), key=_ordering)[:limit]

    def _load(self, role: str, region: str) -> dict[str, MarketSkill]:
        role, region = _label(role), _label(region)
        key = (role.casefold(), region.casefold())
        if key not in self._estimates:
            path = self.cache_dir / f"{_slug(role)}__{_slug(region)}.json"
            rows = self._read_cache(path)
            if rows is None:
                rows = self._estimate(role, region)
                if not rows:
                    # Failures are not cached, so the next request may try again.
                    return {}
                self._write_cache(path, rows)
            self._estimates[key] = {row.skill_id: row for row in rows}
        return self._estimates[key]

    def _estimate(self, role: str, region: str) -> list[MarketSkill]:
        try:
            taxonomy = self._taxonomy or get_taxonomy(self.settings)
            prompt = ESTIMATE_PROMPT.format(
                role=role, region=region, vocabulary=self._vocabulary()
            )
            batch = _request_estimates(self.settings, prompt)
        except Exception:
            logger.warning("LLM demand estimate unavailable for %s/%s", role, region, exc_info=True)
            return []

        model = _model_name(self.settings)
        today = date.today()
        rows: dict[str, MarketSkill] = {}
        for estimate in batch.skills:
            skill_id = taxonomy.normalise(estimate.skill_id)
            if skill_id is None or skill_id in rows:
                continue
            frequency = _usable_frequency(estimate.frequency)
            rows[skill_id] = MarketSkill(
                skill_id=skill_id,
                frequency=frequency,
                role=role,
                region=region,
                provenance=estimated_provenance(
                    model, 0.0 if frequency is None else estimate.confidence, today
                ),
            )
        return sorted(rows.values(), key=_ordering)

    def _vocabulary(self) -> str:
        payload = yaml.safe_load(
            (self.settings.knowledge_data_dir / "skills.yaml").read_text(encoding="utf-8")
        )
        return "\n".join(f"- {row['id']}: {row['name']}" for row in payload["skills"])

    def _read_cache(self, path: Path) -> list[MarketSkill] | None:
        if not path.is_file():
            return None
        try:
            rows = [
                MarketSkill.model_validate(row)
                for row in json.loads(path.read_text(encoding="utf-8"))
            ]
        except (OSError, ValueError):
            logger.warning("Ignoring unreadable LLM demand cache %s", path)
            return None
        # A hand-edited cache must not smuggle an estimate past its label.
        return [
            row.model_copy(
                update={
                    "provenance": row.provenance.model_copy(
                        update={
                            "source_kind": SourceKind.ESTIMATED,
                            "confidence": min(row.provenance.confidence, MAX_CONFIDENCE),
                            "sample_size": None,
                        }
                    )
                }
            )
            for row in rows
        ] or None

    def _write_cache(self, path: Path, rows: list[MarketSkill]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps([row.model_dump(mode="json") for row in rows], indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            logger.warning("Could not write LLM demand cache %s", path, exc_info=True)
