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


class NodeStatus(str, Enum):
    """Evidence standing of a single skill node in the roadmap diagram.

    VERIFIED  = recall or repository evidence proved it
    FAMILIAR  = written in the user's code but never verified
    NEW       = never touched
    """

    VERIFIED = "verified"
    FAMILIAR = "familiar"
    NEW = "new"


class ConceptSkill(BaseModel):
    """A leaf node hanging off a concept box."""

    skill_id: str
    skill_name: str
    status: NodeStatus
    focus: str = Field(description="Short next step, grounded in a real finding where one exists.")
    mastery: float = Field(
        0.0, ge=0.0, le=1.0, description="new 0.0, familiar 0.5, verified 1.0"
    )
    gap_evidence: Evidence | None = Field(
        None, description="The line the finding behind `focus` points at, when there is one."
    )
    related_to: list[str] = Field(
        default_factory=list,
        description="Skills the user already works with that this one builds on.",
    )
    evidence: list[Evidence] = Field(default_factory=list)
    market_frequency: float | None = None
    provenance: Provenance | None = None
    priority: float = 0.0


class RoadmapConcept(BaseModel):
    """A box on the spine. Holds the concept only -- detail lives in `skills`."""

    concept_id: str
    concept_name: str
    summary: str
    mastery: float = Field(0.0, ge=0.0, le=1.0, description="Mean mastery of this concept's skills.")
    verified_count: int = 0
    familiar_count: int = 0
    new_count: int = 0
    priority: float = 0.0
    skills: list[ConceptSkill] = Field(default_factory=list)


class RoadmapGraph(BaseModel):
    """Forward-looking roadmap grouped into concepts for the diagram view."""

    role: str
    region: str
    concepts: list[RoadmapConcept] = Field(default_factory=list)
