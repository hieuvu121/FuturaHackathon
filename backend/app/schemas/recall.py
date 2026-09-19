"""The revision loop: questions, answers, grading."""

from enum import Enum

from pydantic import BaseModel, Field

from .common import Evidence
from .scores import Tier


class QuestionType(str, Enum):
    RECALL = "recall"
    JUSTIFY = "justify"
    TRANSFER = "transfer"
    DEBUG = "debug"
    EXTEND = "extend"


class Question(BaseModel):
    id: str
    type: QuestionType
    target: Evidence = Field(description="The function this question is about")
    target_name: str
    prompt: str
    code_context: str = Field(description="Function + callees + creating commit diff, ~3k tokens")
    skill_ids: list[str] = Field(default_factory=list)


class Answer(BaseModel):
    question_id: str
    submission: str


class GradeResult(BaseModel):
    question_id: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str
    tier_change: dict[str, Tier] = Field(
        default_factory=dict, description="skill_id -> new tier, when a promotion happened"
    )
