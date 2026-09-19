"""The three buckets."""

from enum import Enum

from pydantic import BaseModel, Field

from .common import Evidence, Provenance


class Bucket(str, Enum):
    REVISE = "revise"
    DEEPEN = "deepen"
    LEARN_NEW = "learn_new"


class RoadmapItem(BaseModel):
    skill_id: str
    skill_name: str
    bucket: Bucket
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)
    market_frequency: float | None = None
    provenance: Provenance | None = None
    priority: float = Field(description="frequency x proximity. Degrades gracefully when frequency is None.")


class Buckets(BaseModel):
    role: str
    region: str
    revise: list[RoadmapItem] = Field(default_factory=list)
    deepen: list[RoadmapItem] = Field(default_factory=list)
    learn_new: list[RoadmapItem] = Field(default_factory=list)
