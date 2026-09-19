"""The revision loop. Owner: Track B."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..mock_store import load
from ..models.db import QuestionRow
from ..schemas.findings import Finding
from ..schemas.recall import Answer, GradeResult, Question
from ..schemas.repo_map import RepoMap
from ..services.recall.generator import generate
from ..services.recall.selector import select_targets
from ..services.storage import get_owned_repo, latest_analysis

router = APIRouter(tags=["recall"])


@router.get("/repos/{repo_id}/questions", response_model=list[Question])
def questions(repo_id: str, user: CurrentUser, db: DbDep) -> list[Question]:
    """5 questions from 5 selected target functions."""
    settings = get_settings()
    if settings.mock_mode:
        return [Question.model_validate(q) for q in load("questions")]
    repo = get_owned_repo(db, repo_id, user)
    analysis = latest_analysis(db, repo.id) if repo is not None else None
    if repo is None or analysis is None or analysis.repo_map is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository analysis not found")
    if not repo.clone_path or not Path(repo.clone_path).is_dir():
        raise HTTPException(status.HTTP_409_CONFLICT, "Repository clone is unavailable")

    repo_map = RepoMap.model_validate(analysis.repo_map)
    findings = [Finding.model_validate(item) for item in (analysis.findings or [])]
    generated = generate(
        settings,
        Path(repo.clone_path),
        repo_map,
        select_targets(repo_map, findings),
    )
    generated_ids = {question.id for question in generated}
    stale = db.scalars(select(QuestionRow).where(QuestionRow.repo_id == repo.id)).all()
    for row in stale:
        if row.id not in generated_ids:
            db.delete(row)
    for question in generated:
        row = db.get(QuestionRow, question.id)
        if row is None:
            row = QuestionRow(id=question.id, repo_id=repo.id, type=question.type.value, payload={})
            db.add(row)
        row.repo_id = repo.id
        row.type = question.type.value
        row.payload = question.model_dump(mode="json")
    db.commit()
    return generated


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
