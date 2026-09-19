"""Community: a roadmap shared under a role title, and the reviews it collects."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Standing(str, Enum):
    """Why a reviewer's word carries weight. Earned or granted, never self-declared."""

    MENTOR = "mentor"            # named in knowledge_data/community.yaml
    EXPERIENCED = "experienced"  # has enough verified skills of their own
    MEMBER = "member"


class Verdict(str, Enum):
    VALIDATES = "validates"  # "this roadmap is right for that role"
    SUGGESTS = "suggests"    # "change something"
    COMMENT = "comment"      # neither: a question, thanks, a reply


class SharedConcept(BaseModel):
    name: str
    mastery: float = Field(0.0, ge=0.0, le=1.0)


class SharedStage(BaseModel):
    title: str
    concepts: list[SharedConcept] = Field(default_factory=list)


class CommunityComment(BaseModel):
    id: int
    author: str
    standing: Standing
    verdict: Verdict
    body: str
    created_at: datetime | None = None
    mine: bool = False


class CommunityRoadmap(BaseModel):
    """A snapshot, not a live view: reviews are about the roadmap as it was shared."""

    id: int
    title: str = Field(description="The role this roadmap is for, in the author's words.")
    summary: str = ""
    author: str
    author_standing: Standing = Standing.MEMBER
    overall: float = Field(0.0, ge=0.0, le=1.0)
    stages: list[SharedStage] = Field(default_factory=list)
    validations: int = Field(0, description="Reviews from mentors or experienced users that validate it.")
    suggestions: int = Field(0, description="Reviews from mentors or experienced users that suggest changes.")
    comment_count: int = 0
    is_sample: bool = False
    mine: bool = False
    created_at: datetime | None = None


class CommunityRoadmapDetail(CommunityRoadmap):
    comments: list[CommunityComment] = Field(default_factory=list)
    my_standing: Standing = Field(Standing.MEMBER, description="What badge the viewer's own review would carry.")


class ShareRoadmap(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    summary: str = Field("", max_length=600)


class NewComment(BaseModel):
    body: str = Field(min_length=2, max_length=1_200)
    verdict: Verdict = Verdict.COMMENT
