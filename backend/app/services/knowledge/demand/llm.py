"""LLM-estimated demand. Owner: Track D.

A stopgap for while the real demand source is undecided (plan.md §10).
The model is asked how often a skill appears in job ads for a role and region.

This is a GUESS and must be labelled as one: every row comes back with
source_kind=ESTIMATED, confidence <= 0.4, and sample_size=None, so SourceBadge
renders it visibly weaker than a scraped figure. Never present an estimate as
measurement -- the whole product is an argument against unevidenced claims.

Returning None is always acceptable. The roadmap degrades by design.
"""

from ....config import Settings
from ....schemas.common import Provenance, SourceKind
from ....schemas.market import MarketSkill

MAX_CONFIDENCE = 0.4

ESTIMATE_PROMPT = """Estimate how frequently the skill "{skill}" is named as a
requirement in job advertisements for a {role} role in {region}.

Answer with a single number between 0 and 1, or the word UNKNOWN if you do not
have a reasonable basis for an estimate. Prefer UNKNOWN over a confident guess.
"""


def estimated_provenance(model: str) -> Provenance:
    return Provenance(
        source_kind=SourceKind.ESTIMATED,
        source_name=f"LLM estimate ({model})",
        confidence=MAX_CONFIDENCE,
        sample_size=None,
        collected_at=None,
    )


class LLMDemand:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def frequency(self, skill_id: str, role: str, region: str) -> MarketSkill | None:
        """Return None on UNKNOWN. Do not coerce an unknown into a number."""
        raise NotImplementedError("Track D: call the model, parse, clamp confidence to MAX_CONFIDENCE")

    def top_skills(self, role: str, region: str, limit: int) -> list[MarketSkill]:
        raise NotImplementedError
