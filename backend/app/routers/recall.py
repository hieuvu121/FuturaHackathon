"""The revision loop. Owner: Track B."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, DbDep
from ..mock_store import load
from ..models.db import AnswerRow, QuestionRow, Repo, SkillStatusRow, User
from ..schemas.findings import Finding
from ..schemas.recall import Answer, GradeResult, Question
from ..schemas.recall import QuestionType
from ..schemas.repo_map import RepoMap
from ..services.recall.generator import generate
from ..services.recall.grader import grade
from ..services.recall.injector import inject_bug
from ..services.recall.selector import select_targets
from ..services.storage import get_owned_repo, latest_analysis

router = APIRouter(tags=["recall"])
logger = logging.getLogger(__name__)


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
    root = Path(repo.clone_path)
    selected = select_targets(repo_map, findings)
    open_types = [QuestionType.RECALL, QuestionType.JUSTIFY, QuestionType.TRANSFER]
    generated = generate(settings, root, repo_map, selected[:3], open_types[: len(selected[:3])])
    references: dict[str, dict] = {}

    tested = sorted(
        (function for function in repo_map.functions if function.has_test),
        key=lambda function: (-function.complexity, -function.author_ratio, function.qualified_name),
    )
    if tested:
        try:
            injection = inject_bug(settings, root, tested[0])
        except Exception as exc:
            logger.warning("Debug injection is unavailable: %s", type(exc).__name__)
            injection = None
        if injection is not None:
            debug = generate(settings, root, repo_map, [tested[0]], [QuestionType.DEBUG])[0]
            debug.code_context = injection["broken_code"]
            generated.append(debug)
            references[debug.id] = injection
            extend_target = tested[1] if len(tested) > 1 else tested[0]
            extend = generate(settings, root, repo_map, [extend_target], [QuestionType.EXTEND])[0]
            generated.append(extend)
            references[extend.id] = {"test_command": injection["test_command"]}
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
        row.reference = references.get(question.id)
    db.commit()
    return generated


@router.post("/answers", response_model=GradeResult)
def submit_answer(answer: Answer, user: CurrentUser, db: DbDep) -> GradeResult:
    """Grades, then promotes touched -> verified on transfer-level success."""
    if get_settings().mock_mode:
        return GradeResult(
            question_id=answer.question_id,
            passed=True,
            score=0.8,
            feedback="Mock grading. Track B replaces this with services/recall/grader.py.",
            tier_change={},
        )
    row = db.scalar(
        select(QuestionRow)
        .join(Repo, QuestionRow.repo_id == Repo.id)
        .join(User, Repo.user_id == User.id)
        .where(QuestionRow.id == answer.question_id, User.github_login == user)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    repo = db.get(Repo, row.repo_id)
    question = Question.model_validate(row.payload)
    root = Path(repo.clone_path) if repo.clone_path else None
    result = grade(get_settings(), question, answer, root=root, reference=row.reference or {})
    db.add(
        AnswerRow(
            question_id=question.id,
            submission=answer.submission,
            passed=result.passed,
            score=result.score,
            feedback=result.feedback,
        )
    )
    for skill_id, tier in result.tier_change.items():
        skill = db.scalar(
            select(SkillStatusRow).where(
                SkillStatusRow.user_id == repo.user_id,
                SkillStatusRow.repo_id == repo.id,
                SkillStatusRow.skill_id == skill_id,
            )
        )
        if skill is None:
            skill = SkillStatusRow(
                user_id=repo.user_id,
                repo_id=repo.id,
                skill_id=skill_id,
                evidence=[],
            )
            db.add(skill)
        skill.tier = tier.value
        evidence = question.target.model_dump(mode="json")
        if evidence not in (skill.evidence or []):
            skill.evidence = [*(skill.evidence or []), evidence]
    db.commit()
    return result
