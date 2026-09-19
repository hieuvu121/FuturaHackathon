"""The adaptive loop: one answer decides the next question."""

import pytest

from app.config import Settings
from app.services.recall.adaptive import (
    MAX_LEVEL,
    START_LEVEL,
    Attempt,
    is_bracketed,
    _levels_available,
    load_bank,
    next_question,
)

SETTINGS = Settings()
ORDER = [("python", "Python"), ("sql", "SQL"), ("git", "Git")]


def _available(skill_id: str):
    return _levels_available(load_bank(SETTINGS), skill_id)


def test_the_bank_covers_every_level_the_loop_can_ask_for():
    bank = load_bank(SETTINGS)
    assert bank
    skills = {q.question.skill_ids[0] for q in bank}
    for skill_id in skills:
        levels = set(_available(skill_id))
        assert levels, skill_id
        # A skill the loop starts must be able to move down as well as up.
        if START_LEVEL in levels:
            assert levels & {START_LEVEL - 1, START_LEVEL + 1}, skill_id


def test_a_session_opens_in_the_middle():
    step = next_question(SETTINGS, [], ORDER)

    assert step.question is not None
    assert step.question.level == START_LEVEL
    assert step.question.skill_ids == ["python"]


def test_passing_asks_something_harder():
    attempts = [Attempt("python", 2, True, "python_l2_generator")]

    step = next_question(SETTINGS, attempts, ORDER)

    assert step.question.level > 2
    assert step.question.skill_ids == ["python"]
    assert "harder" in step.reason


def test_failing_drops_the_level():
    attempts = [Attempt("python", 2, False, "python_l2_generator")]

    step = next_question(SETTINGS, attempts, ORDER)

    assert step.question.level < 2
    assert step.question.skill_ids == ["python"]
    assert "easier" in step.reason


def test_a_pass_then_a_fail_brackets_the_skill_and_moves_on():
    attempts = [
        Attempt("python", 2, True, "python_l2_generator"),
        Attempt("python", 3, False, "python_l3_gil"),
    ]

    assert is_bracketed(attempts, "python", _available("python"))
    step = next_question(SETTINGS, attempts, ORDER)
    assert step.question.skill_ids == ["sql"]
    assert step.question.level == START_LEVEL


def test_failing_the_easiest_question_brackets_the_skill():
    attempts = [
        Attempt("python", 2, False, "python_l2_generator"),
        Attempt("python", 1, False, "python_l1_mutable_default"),
    ]

    assert is_bracketed(attempts, "python", _available("python"))
    assert next_question(SETTINGS, attempts, ORDER).question.skill_ids == ["sql"]


def test_clearing_the_top_level_brackets_the_skill():
    attempts = [Attempt("python", MAX_LEVEL, True, "python_l4_context_manager")]

    assert is_bracketed(attempts, "python", _available("python"))


def test_the_loop_finishes_the_skill_in_flight_before_starting_another():
    attempts = [Attempt("sql", 2, True, "sql_l2_nplus1")]

    step = next_question(SETTINGS, attempts, ORDER)

    assert step.question.skill_ids == ["sql"]


def test_a_question_is_never_asked_twice():
    attempts: list[Attempt] = []
    seen: set[str] = set()
    for _ in range(40):
        step = next_question(SETTINGS, attempts, ORDER)
        if step.question is None:
            break
        assert step.question.id not in seen, step.question.id
        seen.add(step.question.id)
        attempts.append(
            Attempt(
                step.question.skill_ids[0],
                step.question.level,
                len(attempts) % 2 == 0,
                step.question.id,
            )
        )
    assert seen


def test_the_session_ends_once_every_skill_is_bracketed():
    attempts = [
        Attempt("python", 2, True, "python_l2_generator"),
        Attempt("python", 3, False, "python_l3_gil"),
        Attempt("sql", 2, True, "sql_l2_nplus1"),
        Attempt("sql", 3, False, "sql_l3_index"),
        Attempt("git", 2, True, "git_l2_rebase_merge"),
        Attempt("git", 3, False, "git_l3_revert"),
    ]

    step = next_question(SETTINGS, attempts, ORDER)

    assert step.question is None
    assert step.remaining_skills == 0


def test_skills_with_no_seeded_questions_are_skipped_not_reported_done():
    step = next_question(SETTINGS, [], [("kubernetes", "Kubernetes"), ("python", "Python")])

    assert step.question is not None
    assert step.question.skill_ids == ["python"]


def test_clearing_the_hardest_question_that_exists_ends_the_skill():
    """data_modelling stops at level 3. Passing it must not drop back to level 1."""
    available = _available("data_modelling")
    assert max(available) == 3, "fixture assumption: this skill has no level 4"

    attempts = [
        Attempt("data_modelling", 2, True, "data_modelling_l2_natural_key"),
        Attempt("data_modelling", 3, True, "data_modelling_l3_scoping"),
    ]

    assert is_bracketed(attempts, "data_modelling", available)
    step = next_question(SETTINGS, attempts, [("data_modelling", "Data Modelling"), ("git", "Git")])
    assert step.question.skill_ids == ["git"]


def test_failing_the_easiest_question_that_exists_ends_the_skill():
    available = _available("postgresql")
    attempts = [Attempt("postgresql", min(available), False, "postgresql_l1_why")]

    assert is_bracketed(attempts, "postgresql", available)
