"""Grades submissions. Owner: Track B.

Unit tests for debug and extend types; rubric-based model grading for open answers.
Promotes skills touched -> verified on transfer-level success or above.
Pushes failed skills into the Revise bucket.
"""

from ...config import Settings
from ...schemas.recall import Answer, GradeResult, Question


def grade(settings: Settings, question: Question, answer: Answer) -> GradeResult:
    raise NotImplementedError
