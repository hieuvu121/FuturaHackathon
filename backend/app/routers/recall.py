"""The revision loop. Owner: Track B."""

from fastapi import APIRouter

from ..config import get_settings
from ..deps import CurrentUser
from ..mock_store import load
from ..schemas.recall import Answer, GradeResult, Question

router = APIRouter(tags=["recall"])


@router.get("/repos/{repo_id}/questions", response_model=list[Question])
def questions(repo_id: str, user: CurrentUser) -> list[Question]:
    """5 questions from 5 selected target functions."""
    if get_settings().mock_mode:
        return [Question.model_validate(q) for q in load("questions")]
    raise NotImplementedError("Track B: selector.py -> generator.py")


@router.post("/answers", response_model=GradeResult)
def submit_answer(answer: Answer, user: CurrentUser) -> GradeResult:
    """Grades, then promotes touched -> verified on transfer-level success."""
    if get_settings().mock_mode:
        return GradeResult(
            question_id=answer.question_id,
            passed=True,
            score=0.8,
            feedback="Mock grading. Track B replaces this with services/recall/grader.py.",
            tier_change={},
        )
    raise NotImplementedError("Track B: services/recall/grader.py")
