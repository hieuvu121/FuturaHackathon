"""Qualitative findings from the LLM scanner, after the validator gate."""

from enum import Enum

from pydantic import BaseModel, Field

from .common import Evidence


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Finding(BaseModel):
    id: str
    dimension: str = Field(description="Dimension id from dimensions.yaml")
    severity: Severity
    observation: str
    evidence: Evidence = Field(description="Mandatory. validator.py drops findings without a resolvable one.")
    confidence: float = Field(ge=0.0, le=1.0)
