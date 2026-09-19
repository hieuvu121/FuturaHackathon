"""Grading for the seeded drill bank. Owner: Track B.

Two graders, in order of preference:

  1. the model, given the question and its seeded key points as the rubric
  2. key-point overlap, computed here

The fallback is not a placeholder. A drill is graded on whether the answer
names the things that matter, and the key points ARE those things, so counting
how many appear is a defensible measure on its own. It exists because a demo
that stops working when an API call times out is worse than one that grades a
little more bluntly, and because the loop only needs pass/fail to pick the next
question.

Grading is coaching, not examination: feedback always says what was missing,
and a failure lowers the next question's level rather than ending anything.
"""

import json
import logging
import re

import anthropic
from openai import OpenAI
from pydantic import BaseModel, Field

from ...config import Settings
from ...schemas.recall import Answer, QuestionType
from .adaptive import BankEntry

logger = logging.getLogger(__name__)

PASS_MARK = 0.5
REQUEST_TIMEOUT_SECONDS = 30
STOPWORDS = {
    "a", "an", "the", "is", "are", "of", "to", "in", "on", "for", "and", "or",
    "it", "its", "at", "by", "be", "as", "that", "this", "with", "when", "not",
}


class DrillVerdict(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    feedback: str
    missing: list[str] = Field(default_factory=list)


class ModelJudgement(BaseModel):
    """What the model is asked for: a judgement, never a number.

    Asking it to score directly proved unreliable -- it returned 0.0 alongside
    feedback describing three of four key points as made. Judging which points
    an answer covers is what it is good at, so it does that and the score is
    computed here.
    """

    made: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    feedback: str


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+]+", text.casefold()) if w not in STOPWORDS}


def _covers(key_point: str, answer_words: set[str]) -> bool:
    """A key point counts as made when most of its significant words appear."""
    needed = _words(key_point)
    if not needed:
        return False
    hits = len(needed & answer_words)
    return hits / len(needed) >= 0.6


def grade_by_key_points(entry: BankEntry, submission: str) -> DrillVerdict:
    """Deterministic fallback: how much of the rubric did the answer name?"""
    if not entry.key_points:
        return DrillVerdict(score=0.0, feedback="This drill has no rubric to grade against.")
    answer_words = _words(submission)
    made = [point for point in entry.key_points if _covers(point, answer_words)]
    missing = [point for point in entry.key_points if point not in made]
    score = len(made) / len(entry.key_points)
    if score >= PASS_MARK:
        tail = f" You did not mention {', '.join(missing)}." if missing else ""
        return DrillVerdict(
            score=score,
            feedback=f"That covers the main idea.{tail}",
            missing=missing,
        )
    return DrillVerdict(
        score=score,
        feedback=f"Not quite. The part that matters here is {', '.join(missing[:3])}.",
        missing=missing,
    )


def _prompt(entry: BankEntry, submission: str) -> str:
    return json.dumps(
        {
            "instruction": (
                "Judge this revision drill as coaching, not an exam. For each key "
                "point, decide whether the answer makes it -- wording need not "
                "match, the idea must be there. Put each key point in exactly one "
                "of `made` or `missing`, copied verbatim. Then write one or two "
                "sentences of feedback naming what was missed. Do not invent "
                "criteria beyond the key points, and do not score."
            ),
            "question": entry.question.prompt,
            "kind": entry.question.type.value,
            # Present for drills written against the user's repository: the task
            # is about this code, so the judge has to see it too.
            "code_context": entry.question.code_context,
            "key_points": entry.key_points,
            "reference_solution": entry.solution,
            "answer": submission,
        }
    )


def _from_judgement(entry: BankEntry, judgement: ModelJudgement) -> DrillVerdict:
    """Score by counting, so a mis-stated number cannot fail a good answer."""
    total = len(entry.key_points) or 1
    made = [point for point in entry.key_points if point in judgement.made]
    missing = [point for point in entry.key_points if point not in made]
    return DrillVerdict(
        score=len(made) / total,
        feedback=judgement.feedback,
        missing=missing,
    )


def _grade_with_model(settings: Settings, entry: BankEntry, submission: str) -> DrillVerdict:
    prompt = _prompt(entry, submission)
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        response = OpenAI(
            api_key=settings.openai_api_key, timeout=REQUEST_TIMEOUT_SECONDS
        ).responses.parse(
            model=settings.grader_model
            if not settings.grader_model.startswith("claude")
            else settings.scanner_model,
            input=[{"role": "user", "content": prompt}],
            text_format=ModelJudgement,
        )
        if response.output_parsed is None:
            raise RuntimeError("Grader returned no structured verdict")
        return _from_judgement(entry, response.output_parsed)
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    message = anthropic.Anthropic(
        api_key=settings.anthropic_api_key, timeout=REQUEST_TIMEOUT_SECONDS
    ).messages.create(
        model=settings.grader_model,
        max_tokens=600,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": prompt
                + '\nReturn ONLY JSON: {"made":["..."],"missing":["..."],"feedback":"..."}',
            }
        ],
    )
    text = "\n".join(block.text for block in message.content if block.type == "text")
    return _from_judgement(entry, ModelJudgement.model_validate_json(text))


def grade_choice(entry: BankEntry, submission: str) -> DrillVerdict:
    """A multiple-choice drill has one right option, so no model and no judgement call."""
    if submission.strip() == entry.answer.strip():
        return DrillVerdict(score=1.0, feedback="That is the one.")
    return DrillVerdict(
        score=0.0,
        feedback="Not that one. Compare your pick with the answer below and see what it misses.",
        missing=entry.key_points,
    )


def grade_drill(settings: Settings, entry: BankEntry, answer: Answer) -> DrillVerdict:
    """Multiple choice by exact match. Otherwise the model first, and key points
    if the model is unavailable or misbehaves."""
    if not answer.submission.strip():
        return DrillVerdict(score=0.0, feedback="Nothing to grade yet.", missing=entry.key_points)
    if entry.answer:
        return grade_choice(entry, answer.submission)
    try:
        return _grade_with_model(settings, entry, answer.submission)
    except Exception as exc:
        logger.info(
            "Drill grader falling back to key points for %s: %s",
            entry.question.id,
            type(exc).__name__,
        )
        return grade_by_key_points(entry, answer.submission)


def model_answer(entry: BankEntry) -> str:
    """What to show after grading, so a miss still teaches something."""
    # A coding drill shows its reference solution, an explain drill its model explanation.
    if entry.question.type in (QuestionType.CODING, QuestionType.EXPLAIN) and entry.solution:
        return entry.solution
    if entry.answer:
        return entry.answer
    return "Key points: " + "; ".join(entry.key_points) if entry.key_points else ""
