"""Evidence and Provenance.

Every claim the system makes carries one or both of these. A score without
Evidence is an opinion; a market figure without Provenance is a rumour.
"""

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """A pointer into the cached clone. Never holds source code itself."""

    file: str = Field(description="Path relative to the repository root")
    lines: tuple[int, int] = Field(description="Inclusive 1-based (start, end)")
    commit: str | None = Field(default=None, description="Commit SHA the pointer is valid at")


class SourceKind(str, Enum):
    SEEDED = "seeded"       # hand-written by the team
    SCRAPED = "scraped"     # derived from collected job ads
    EXTERNAL = "external"   # a standard published dataset
    ESTIMATED = "estimated" # an LLM's guess. Always the weakest claim; label it as such.


class Provenance(BaseModel):
    """Where a non-code claim came from, and how much to trust it."""

    source_kind: SourceKind
    source_name: str = Field(description="e.g. 'skills.yaml', 'seek.com.au 2026-09'")
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int | None = None
    collected_at: date | None = None
