"""The roadmap's final stage: one project that applies what the roadmap taught."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CapstoneRequirement(BaseModel):
    id: str
    skill_id: str | None = Field(None, description="None for the baseline every project must meet.")
    skill_name: str = ""
    text: str


class CapstoneBrief(BaseModel):
    """What to build. Derived from the user's own roadmap, so two users get different briefs."""

    title: str
    summary: str
    target_skills: list[str] = Field(default_factory=list)
    requirements: list[CapstoneRequirement] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    ready: bool = Field(False, description="Whether the roadmap suggests the user is ready to start.")
    readiness_note: str = ""


class RequirementVerdict(str, Enum):
    MET = "met"
    PARTIAL = "partial"
    MISSING = "missing"


class RequirementReview(BaseModel):
    requirement_id: str
    verdict: RequirementVerdict
    comment: str
    files: list[str] = Field(
        default_factory=list,
        description="Files in the submission that back the verdict. Only paths that exist survive.",
    )


class CapstoneReview(BaseModel):
    summary: str
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    requirements: list[RequirementReview] = Field(default_factory=list)
    score: float = Field(0.0, ge=0.0, le=1.0, description="Counted from the verdicts, never asked of the model.")
    files_reviewed: int = 0
    sample: bool = Field(False, description="True for the canned review served in mock mode.")


class SubmissionStatus(str, Enum):
    REVIEWING = "reviewing"
    REVIEWED = "reviewed"
    FAILED = "failed"


class CapstoneSubmission(BaseModel):
    id: int
    repo_url: str
    notes: str = ""
    status: SubmissionStatus
    error: str | None = None
    review: CapstoneReview | None = None
    submitted_at: datetime | None = None


class CapstoneSubmit(BaseModel):
    repo_url: str = Field(description="https://github.com/<owner>/<repository>")
    notes: str = Field("", max_length=2_000, description="Anything the reviewer should know.")


class CapstoneState(BaseModel):
    brief: CapstoneBrief
    submission: CapstoneSubmission | None = None
