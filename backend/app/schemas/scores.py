"""Per-dimension levels and skill tiers."""

from enum import Enum

from pydantic import BaseModel, Field

from .common import Evidence


class Tier(str, Enum):
    TOUCHED = "touched"
    VERIFIED = "verified"


class DimensionScore(BaseModel):
    dimension: str
    level: int = Field(ge=1, le=4)
    rationale: str
    evidence: list[Evidence] = Field(default_factory=list)
    metric_basis: dict[str, float | int | str] = Field(
        default_factory=dict,
        description="The numbers that drove the level, e.g. {'median_complexity': 14, 'test_ratio': 0.2}",
    )


class SkillStatus(BaseModel):
    skill_id: str
    tier: Tier
    evidence: list[Evidence] = Field(default_factory=list)


class Scores(BaseModel):
    repo: str
    dimensions: list[DimensionScore] = Field(default_factory=list)
    skills: list[SkillStatus] = Field(default_factory=list)
