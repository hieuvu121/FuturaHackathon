"""Grades submissions. Owner: Track B.

Unit tests for debug and extend types; rubric-based model grading for open answers.
Promotes skills touched -> verified on transfer-level success or above.
Pushes failed skills into the Revise bucket.
"""

import json
from pathlib import Path
import shlex
import shutil
import tempfile

import anthropic
from openai import OpenAI
from pydantic import BaseModel, Field
import yaml

from ...config import Settings
from ...schemas.recall import Answer, GradeResult, Question, QuestionType
from ...schemas.scores import Tier
from .injector import _replace_function, _run_tests, _test_command


class RubricResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    feedback: str


def _criteria(settings: Settings, question_type: QuestionType) -> list[str]:
    payload = yaml.safe_load(
        (settings.knowledge_data_dir / "questions.yaml").read_text(encoding="utf-8")
    )
    return payload["question_types"][question_type.value].get("reference_criteria", [])


def _grade_open(settings: Settings, question: Question, answer: Answer) -> RubricResult:
    prompt = json.dumps(
        {
            "instruction": "Grade as revision coaching, not an exam. Use only the criteria and code context.",
            "question": question.prompt,
            "code_context": question.code_context,
            "criteria": _criteria(settings, question.type),
            "answer": answer.submission,
        }
    )
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        response = OpenAI(api_key=settings.openai_api_key).responses.parse(
            model=(
                settings.scanner_model
                if settings.grader_model.casefold().startswith("claude")
                else settings.grader_model
            ),
            input=[{"role": "user", "content": prompt}],
            text_format=RubricResult,
        )
        if response.output_parsed is None:
            raise RuntimeError("Grader returned no structured result")
        return response.output_parsed
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    response = anthropic.Anthropic(api_key=settings.anthropic_api_key).messages.create(
        model=settings.grader_model,
        max_tokens=800,
        temperature=0,
        messages=[{"role": "user", "content": prompt + "\nReturn JSON with score and feedback."}],
    )
    text = "\n".join(block.text for block in response.content if block.type == "text")
    return RubricResult.model_validate(json.loads(text))


def _grade_with_tests(root: Path, question: Question, answer: Answer, reference: dict) -> RubricResult:
    command_text = reference.get("test_command")
    command = shlex.split(command_text) if command_text else _test_command()
    with tempfile.TemporaryDirectory(prefix="futura-grade-") as temp_dir:
        workspace = Path(temp_dir) / "repo"
        shutil.copytree(root, workspace, ignore=shutil.ignore_patterns(".git", ".venv", "venv"))
        _replace_function(
            workspace,
            type("Target", (), {"file": question.target.file, "lines": question.target.lines})(),
            answer.submission,
        )
        result = _run_tests(workspace, command)
    if result.returncode == 0:
        return RubricResult(score=1.0, feedback="Your revision passes the repository test suite.")
    output = (result.stdout + "\n" + result.stderr).strip()[-1_500:]
    return RubricResult(
        score=0.0,
        feedback=f"The revision still needs work; the verification tests did not pass.\n{output}",
    )


def grade(
    settings: Settings,
    question: Question,
    answer: Answer,
    *,
    root: Path | None = None,
    reference: dict | None = None,
) -> GradeResult:
    if answer.question_id != question.id:
        raise ValueError("Answer does not match the question")
    if not answer.submission.strip():
        return GradeResult(
            question_id=question.id,
            passed=False,
            score=0.0,
            feedback="Add your reasoning or revision so there is something to review.",
        )
    if question.type in {QuestionType.DEBUG, QuestionType.EXTEND}:
        if root is None:
            raise ValueError("Unit-test grading requires the repository clone")
        result = _grade_with_tests(root, question, answer, reference or {})
    else:
        result = _grade_open(settings, question, answer)
    passed = result.score >= 0.7
    promotes = question.type in {QuestionType.TRANSFER, QuestionType.DEBUG, QuestionType.EXTEND}
    return GradeResult(
        question_id=question.id,
        passed=passed,
        score=result.score,
        feedback=result.feedback,
        tier_change={skill_id: Tier.VERIFIED for skill_id in question.skill_ids}
        if passed and promotes
        else {},
    )
