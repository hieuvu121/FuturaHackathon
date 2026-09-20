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


class LearningResource(BaseModel):
    """Somewhere outside the product to go and learn the skill."""

    title: str
    url: str
    kind: str = Field("guide", description="docs | guide | course | practice | reference")


class ConceptSkill(BaseModel):
    """A leaf node hanging off a concept box."""

    skill_id: str
    skill_name: str
    status: NodeStatus
    focus: str = Field(description="Short next step, grounded in a real finding where one exists.")
    mastery: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Untested: new 0.0, familiar 0.5, verified 1.0. "
            "Once recall has tested the skill: hardest drill level passed / 4."
        ),
    )
    missing: str = Field(
        "",
        description=(
            "Two or three sentences on what stands between the user and this skill, "
            "built from their repository evidence, scanner findings and recall results."
        ),
    )
    resources: list[LearningResource] = Field(
        default_factory=list, description="External study material for this skill."
    )
    hidden: bool = Field(
        False, description="The user tailored this skill out. Only ever true when hidden skills were asked for."
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
    stage: int = Field(1, ge=1, description="Which step of the learning order this concept belongs to.")
    skills: list[ConceptSkill] = Field(default_factory=list)


class RoadmapStage(BaseModel):
    """One step of the learning order. Concepts in the same stage are learnt side by side."""

    index: int = Field(ge=1)
    title: str
    note: str
    concept_ids: list[str] = Field(default_factory=list)


class ReviewStatus(str, Enum):
    PENDING = "pending"    # shown to the user, not yet agreed
    ACCEPTED = "accepted"


class RoadmapReview(BaseModel):
    """Whether the user has agreed that this roadmap describes them."""

    status: ReviewStatus = ReviewStatus.PENDING
    hidden_skills: list[str] = Field(default_factory=list)
    recall_answered: int = Field(0, description="Answers in the current recall session.")
    recall_session_length: int = 5


class TailorRequest(BaseModel):
    hidden_skills: list[str] = Field(default_factory=list, max_length=200)


class RoadmapGraph(BaseModel):
    """Forward-looking roadmap grouped into concepts for the diagram view."""

    role: str
    region: str
    role_name: str = Field("", description="The role in words, when the roadmap was built for one.")
    source: str = Field(
        "repos", description="'repos' when built from analysed code, 'survey' when built from the onboarding survey."
    )
    concepts: list[RoadmapConcept] = Field(default_factory=list)
    stages: list[RoadmapStage] = Field(
        default_factory=list,
        description="The order to learn the concepts in. Every concept appears in exactly one stage.",
    )
