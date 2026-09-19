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
from ..schemas.recall import GENERATED_TYPES, QuestionType
from ..schemas.repo_map import RepoMap
from ..services.portfolio import build_profile, owned_selected_repos
from ..services.recall.generator import generate, personalize_for_portfolio
from ..services.recall.grader import grade
from ..services.recall.injector import inject_bug
from ..services.recall.selector import select_targets
from ..services.storage import get_owned_repo, latest_analysis

router = APIRouter(tags=["recall"])
logger = logging.getLogger(__name__)


def _persist_questions(
    db: DbDep,
    generated: list[Question],
    references: dict[str, dict],
    portfolio_repo_ids: list[str],
) -> None:
    """Persist public prompts while keeping grading references server-side."""
    repo_ids = {int(question.target.repo_id) for question in generated if question.target.repo_id}
    generated_ids = {question.id for question in generated}
    if repo_ids:
        stale = db.scalars(select(QuestionRow).where(QuestionRow.repo_id.in_(repo_ids))).all()
        for row in stale:
            if row.id not in generated_ids:
                db.delete(row)
    question_ids = sorted(question.id for question in generated)
    for question in generated:
        if question.target.repo_id is None:
            raise ValueError("Generated portfolio questions must identify their repository")
        repo_id = int(question.target.repo_id)
        row = db.get(QuestionRow, question.id)
        if row is None:
            row = QuestionRow(id=question.id, repo_id=repo_id, type=question.type.value, payload={})
            db.add(row)
        row.repo_id = repo_id
        row.type = question.type.value
        row.payload = question.model_dump(mode="json")
        row.reference = {
            **references.get(question.id, {}),
            "_portfolio_repo_ids": sorted(portfolio_repo_ids),
            "_portfolio_question_ids": question_ids,
        }
    db.commit()


@router.get("/repos/portfolio/questions", response_model=list[Question])
def portfolio_questions(user: CurrentUser, db: DbDep) -> list[Question]:
    """Generate questions using all selected repositories as one capability portfolio."""
    settings = get_settings()
    if settings.mock_mode:
        return [Question.model_validate(q) for q in load("questions")]
    repos = owned_selected_repos(db, user)
    if not repos:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No repositories are selected")
    portfolio_key = sorted(str(repo.id) for repo in repos)
    cached_rows = db.scalars(
        select(QuestionRow).where(QuestionRow.repo_id.in_([repo.id for repo in repos]))
    ).all()
    cached_rows_for_portfolio = [
        row
        for row in cached_rows
        if (row.reference or {}).get("_portfolio_repo_ids") == portfolio_key
    ]
    cached = [
        Question.model_validate(row.payload)
        for row in cached_rows_for_portfolio
    ]
    expected_ids = set(
        (cached_rows_for_portfolio[0].reference or {}).get("_portfolio_question_ids", [])
    ) if cached_rows_for_portfolio else set()
    if cached and expected_ids == {question.id for question in cached}:
        order = {question_type: index for index, question_type in enumerate(GENERATED_TYPES)}
        return sorted(cached, key=lambda question: order[question.type])

    contexts: list[tuple[Repo, Path, RepoMap, list[Finding]]] = []
    for repo in repos:
        analysis = latest_analysis(db, repo.id)
        if analysis is None or analysis.repo_map is None:
            continue
        if not repo.clone_path or not Path(repo.clone_path).is_dir():
            continue
        contexts.append(
            (
                repo,
                Path(repo.clone_path),
                RepoMap.model_validate(analysis.repo_map),
                [Finding.model_validate(item) for item in (analysis.findings or [])],
            )
        )
    if not contexts:
        raise HTTPException(status.HTTP_409_CONFLICT, "No selected repository is ready for questions")

    # Round-robin the open questions so one large repository does not dominate the portfolio.
    candidates = []
    for repo, root, repo_map, findings in contexts:
        targets = select_targets(repo_map, findings, limit=3)
        if not targets:
            # A demo portfolio may not contain a hotspot in the narrow 30–90 day window.
            # Keep the same evidence quality while falling back to the strongest authored code.
            targets = sorted(
                (function for function in repo_map.functions if not function.has_test),
                key=lambda function: (
                    -function.complexity,
                    -function.author_ratio,
                    -function.times_modified,
                    function.qualified_name,
                ),
            )[:3]
        candidates.append((repo, root, repo_map, targets))
    generated: list[Question] = []
    open_types = [QuestionType.RECALL, QuestionType.JUSTIFY, QuestionType.TRANSFER]
    for index, question_type in enumerate(open_types):
        for offset in range(len(candidates)):
            repo, root, repo_map, targets = candidates[(index + offset) % len(candidates)]
            if targets:
                target = targets.pop(0)
                generated.extend(
                    generate(
                        settings,
                        root,
                        repo_map,
                        [target],
                        [question_type],
                        repo_id=str(repo.id),
                    )
                )
                break

    references: dict[str, dict] = {}
    tested = sorted(
        (
            (repo, root, repo_map, function)
            for repo, root, repo_map, _ in contexts
            for function in repo_map.functions
            if function.has_test
        ),
        key=lambda item: (-item[3].complexity, -item[3].author_ratio, item[3].qualified_name),
    )
    if tested:
        repo, root, repo_map, target = tested[0]
        try:
            injection = inject_bug(settings, root, target)
        except Exception as exc:
            logger.warning("Portfolio debug injection is unavailable: %s", type(exc).__name__)
            injection = None
        if injection is not None:
            debug = generate(
                settings,
                root,
                repo_map,
                [target],
                [QuestionType.DEBUG],
                repo_id=str(repo.id),
            )[0]
            debug.code_context = injection["broken_code"]
            generated.append(debug)
            references[debug.id] = injection

            extend_repo, extend_root, extend_map, extend_target = tested[1] if len(tested) > 1 else tested[0]
            extend = generate(
                settings,
                extend_root,
                extend_map,
                [extend_target],
                [QuestionType.EXTEND],
                repo_id=str(extend_repo.id),
            )[0]
            generated.append(extend)
            references[extend.id] = {
                "test_command": injection["test_command"] if extend_root == root else ""
            }

    if not generated:
        raise HTTPException(status.HTTP_409_CONFLICT, "No suitable portfolio question targets found")
    try:
        profile = build_profile(db, user)
        generated = personalize_for_portfolio(
            settings,
            generated,
            {
                "repositories": [item.model_dump(mode="json") for item in profile.repositories],
                "dimensions": [item.model_dump(mode="json") for item in profile.scores.dimensions],
                "skills": [item.model_dump(mode="json") for item in profile.scores.skills],
                "top_findings": [
                    item.model_dump(mode="json") for item in profile.findings[:12]
                ],
            },
        )
    except Exception as exc:
        logger.warning("Portfolio question generation failed: %s", type(exc).__name__)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Portfolio question generation is temporarily unavailable",
        ) from exc
    _persist_questions(db, generated, references, portfolio_key)
    return generated


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
