"""Practice: a topic, three kinds of question, and nothing that touches the roadmap."""

import pytest

from app.config import Settings
from app.routers import drills as drills_router
from app.schemas.recall import Answer, QuestionType
from app.services.knowledge import get_taxonomy
from app.services.recall import practice
from app.services.recall.adaptive import load_bank

SETTINGS = Settings(mock_mode=True, openai_api_key="", anthropic_api_key="")


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(drills_router, "get_settings", lambda: SETTINGS)


def test_python_and_fastapi_are_seeded_with_all_three_kinds():
    topics = {topic.skill_id: topic for topic in practice.topics(SETTINGS)}

    assert {"python", "fastapi"} <= set(topics)
    taxonomy = get_taxonomy(SETTINGS)
    for skill_id, topic in topics.items():
        assert taxonomy.normalise(skill_id) == skill_id
        assert topic.summary
        assert set(topic.counts) == {"concept", "coding", "explain"}
        assert all(count >= 2 for count in topic.counts.values()), (skill_id, topic.counts)


def test_questions_can_be_filtered_by_kind_and_come_easiest_first():
    everything = drills_router.practice_questions("fastapi", "dev")
    explain = drills_router.practice_questions("fastapi", "dev", QuestionType.EXPLAIN)

    assert [q.level for q in everything] == sorted(q.level for q in everything)
    assert explain and all(q.type is QuestionType.EXPLAIN for q in explain)
    assert all(q.skill_ids == ["fastapi"] for q in everything)


def test_each_kind_has_the_shape_the_page_needs():
    for topic in practice.topics(SETTINGS):
        for question in practice.questions(SETTINGS, topic.skill_id):
            if question.type is QuestionType.CONCEPT:
                assert len(question.choices) == 4 and not question.code_context
            elif question.type is QuestionType.CODING:
                assert question.starter and not question.choices
            else:
                assert question.code_context and not question.choices
            assert question.target is None


def test_answers_and_rubrics_never_ride_along_on_the_question():
    for topic in practice.topics(SETTINGS):
        for question in practice.questions(SETTINGS, topic.skill_id):
            entry = practice.entry_for(SETTINGS, question.id)
            sent = question.model_dump_json()
            assert entry.solution[:40] not in sent if entry.solution else True
            for point in entry.key_points:
                assert f'"{point}"' not in sent


def test_an_unknown_topic_is_a_404():
    with pytest.raises(Exception) as caught:
        drills_router.practice_questions("cobol", "dev")
    assert getattr(caught.value, "status_code", None) == 404


def test_multiple_choice_is_graded_by_exact_match():
    question = drills_router.practice_questions("python", "dev", QuestionType.CONCEPT)[0]
    entry = practice.entry_for(SETTINGS, question.id)
    wrong = next(choice for choice in question.choices if choice != entry.answer)

    right = drills_router.practice_answer(Answer(question_id=question.id, submission=entry.answer), "dev")
    missed = drills_router.practice_answer(Answer(question_id=question.id, submission=wrong), "dev")

    assert right.passed and right.score == 1.0
    assert not missed.passed and missed.model_answer == entry.answer


def test_an_explanation_is_graded_on_its_key_points_and_shown_a_model_answer():
    question = drills_router.practice_questions("fastapi", "dev", QuestionType.EXPLAIN)[0]
    entry = practice.entry_for(SETTINGS, question.id)

    good = drills_router.practice_answer(
        Answer(question_id=question.id, submission=". ".join(entry.key_points)), "dev"
    )
    vague = drills_router.practice_answer(Answer(question_id=question.id, submission="It gets a user."), "dev")

    assert good.passed
    assert not vague.passed and vague.missing
    assert vague.model_answer == entry.solution


def test_the_evaluation_bank_has_explain_drills_that_carry_their_code():
    explain = [e for e in load_bank(SETTINGS) if e.question.type is QuestionType.EXPLAIN]

    assert len(explain) >= 5
    for entry in explain:
        assert entry.question.code_context, entry.question.id
        assert entry.key_points and entry.solution, entry.question.id
        assert entry.question.choices == [] and entry.answer == ""
