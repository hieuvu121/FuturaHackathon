"""Market demand. Frequency is nullable BY DESIGN.

The roadmap must still produce output when demand data is None
(OVERALL.md section 1, final invariant).
"""

from pydantic import BaseModel, Field

from .common import Provenance


class MarketSkill(BaseModel):
    skill_id: str
    frequency: float | None = Field(
        default=None,
        description="Share of job ads mentioning this skill. None = unknown, not zero.",
    )
    role: str
    region: str
    provenance: Provenance
