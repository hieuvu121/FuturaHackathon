"""Portfolio-level contracts across the user's selected repositories."""

from pydantic import BaseModel, Field

from .findings import Finding
from .scores import Scores


class PortfolioSelectionRequest(BaseModel):
    repo_ids: list[str] = Field(min_length=3, max_length=5)


class PortfolioRepoSummary(BaseModel):
    id: str
    full_name: str
    language: str | None = None
    stage: str = "not_started"
    progress: int = 0


class PortfolioSelectionResponse(BaseModel):
    repositories: list[PortfolioRepoSummary] = Field(default_factory=list)


class PortfolioProfile(BaseModel):
    repositories: list[PortfolioRepoSummary]
    total_files: int
    total_functions: int
    excluded_files: int
    scores: Scores
    findings: list[Finding] = Field(default_factory=list)
