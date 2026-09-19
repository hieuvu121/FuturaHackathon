"""Grading the seeded drills, and the fallback that keeps a demo alive."""

from dataclasses import replace

from app.config import Settings
from app.schemas.recall import Answer, QuestionType
from app.services.recall.adaptive import entry_for, load_bank
from app.services.recall.drills import (
    PASS_MARK,
    grade_by_key_points,
    grade_drill,
    model_answer,
)

SETTINGS = Settings()


def test_an_answer_naming_the_key_points_passes():
    entry = entry_for(SETTINGS, "sql_l2_nplus1")

    verdict = grade_by_key_points(
        entry,
        "It is one query per row: a loop issuing queries for each result. "
        "Fix it with a join or eager load so you batch the work.",
    )

    assert verdict.score >= PASS_MARK
    assert "covers" in verdict.feedback


def test_an_empty_gesture_fails_and_says_what_was_wanted():
    entry = entry_for(SETTINGS, "sql_l2_nplus1")

    verdict = grade_by_key_points(entry, "not sure")

    assert verdict.score < PASS_MARK
    assert verdict.missing
    assert "Not quite" in verdict.feedback


def test_a_blank_submission_is_never_sent_to_a_model():
    entry = entry_for(SETTINGS, "sql_l2_nplus1")

    # Settings carry no key here, so reaching a provider would raise rather
    # than return -- this passing proves the short circuit.
    verdict = grade_drill(Settings(openai_api_key="", anthropic_api_key=""), entry, Answer(question_id=entry.question.id, submission="   "))

    assert verdict.score == 0.0


def test_grading_falls_back_to_key_points_when_no_provider_is_configured():
    # A drill with no options is still free text, and still has to survive a dead provider.
    entry = replace(entry_for(SETTINGS, "sql_l2_nplus1"), answer="")
    offline = Settings(openai_api_key="", anthropic_api_key="", llm_provider="openai")

    verdict = grade_drill(
        offline,
        entry,
        Answer(
            question_id=entry.question.id,
            submission="One query per row inside a loop issuing queries; use a join or eager load to batch.",
        ),
    )

    assert verdict.score >= PASS_MARK


def test_a_coding_drill_shows_its_reference_solution_afterwards():
    entry = entry_for(SETTINGS, "python_l2_dedupe")

    assert entry.question.type is QuestionType.CODING
    assert entry.question.starter
    assert "seen" in model_answer(entry)


def test_a_free_text_concept_drill_shows_its_key_points_afterwards():
    entry = replace(entry_for(SETTINGS, "async_l2_event_loop"), answer="")

    assert model_answer(entry).startswith("Key points:")


def test_a_multiple_choice_drill_shows_the_right_option_afterwards():
    entry = entry_for(SETTINGS, "async_l2_event_loop")

    assert model_answer(entry) == entry.answer
    assert entry.answer in entry.question.choices


def test_every_concept_drill_is_multiple_choice_and_no_coding_drill_is():
    for entry in load_bank(SETTINGS):
        if entry.question.type is QuestionType.CONCEPT:
            assert len(entry.question.choices) == 4, entry.question.id
            assert len(set(entry.question.choices)) == 4, entry.question.id
            assert entry.answer in entry.question.choices, entry.question.id
        else:
            assert entry.question.choices == [], entry.question.id
            assert entry.answer == "", entry.question.id


def test_option_order_gives_nothing_away():
    concept = [e for e in load_bank(SETTINGS) if e.question.choices]
    positions = [e.question.choices.index(e.answer) for e in concept]

    # The file lists the right option first; the browser must not see that.
    assert all(positions.count(slot) >= len(concept) // 8 for slot in range(4))
    # And it has to be the same order every time, or a refresh reshuffles the page.
    assert [e.question.choices for e in load_bank(SETTINGS) if e.question.choices] == [
        e.question.choices for e in concept
    ]


def test_answer_length_gives_nothing_away():
    concept = [e for e in load_bank(SETTINGS) if e.question.choices]
    longest = sum(1 for e in concept if len(e.answer) == max(map(len, e.question.choices)))
    shortest = sum(1 for e in concept if len(e.answer) == min(map(len, e.question.choices)))

    assert longest <= len(concept) // 2
    assert shortest <= len(concept) // 2


def test_a_multiple_choice_drill_is_graded_by_exact_match_without_a_model():
    entry = entry_for(SETTINGS, "sql_l2_nplus1")
    offline = Settings(openai_api_key="", anthropic_api_key="", llm_provider="openai")
    wrong = next(option for option in entry.question.choices if option != entry.answer)

    right = grade_drill(offline, entry, Answer(question_id=entry.question.id, submission=entry.answer))
    missed = grade_drill(offline, entry, Answer(question_id=entry.question.id, submission=wrong))

    assert right.score == 1.0
    assert missed.score == 0.0
    assert missed.missing == entry.key_points


def test_key_points_never_reach_the_browser():
    """The rubric is the answer. It must not ride along on the question."""
    for entry in load_bank(SETTINGS):
        payload = entry.question.model_dump()
        assert "key_points" not in payload
        assert "solution" not in payload


def test_the_score_is_counted_here_not_taken_from_the_model():
    """A model that judges well but states a wrong number must not fail a good answer."""
    from app.services.recall.drills import ModelJudgement, _from_judgement

    entry = entry_for(SETTINGS, "data_modelling_l2_natural_key")
    judgement = ModelJudgement(
        made=["can change", "business meaning", "surrogate key is stable"],
        missing=["wide"],
        feedback="Good coverage; you did not mention that natural keys are often wide.",
    )

    verdict = _from_judgement(entry, judgement)

    assert verdict.score == 3 / 4
    assert verdict.score >= PASS_MARK
    assert verdict.missing == ["wide"]


def test_a_key_point_the_model_invents_cannot_inflate_the_score():
    from app.services.recall.drills import ModelJudgement, _from_judgement

    entry = entry_for(SETTINGS, "data_modelling_l2_natural_key")
    judgement = ModelJudgement(made=["something nobody asked for"], missing=[], feedback="ok")

    verdict = _from_judgement(entry, judgement)

    assert verdict.score == 0.0
    assert verdict.missing == entry.key_points
