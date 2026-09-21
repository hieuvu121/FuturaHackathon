"""Practice: recall a topic by doing it, three ways.

The evaluation (adaptive.py) is a search for the user's level, and it feeds
the roadmap. Practice is what comes after: pick a topic, and work through
multiple-choice, coding and explain-this-code questions about it. Nothing here
moves the roadmap -- it is a place to get better, not to be measured -- so it
keeps no state and has no session to finish.

Questions live in knowledge_data/practice_bank.yaml and are graded by the same
graders as the evaluation drills, so a miss still comes back with what was
wanted and a model answer.
"""

import functools

import yaml
from pydantic import BaseModel, Field

from ...config import Settings
from ...schemas.recall import Question, QuestionType
from .adaptive import BankEntry, _shuffled

PRACTICE_KINDS: tuple[QuestionType, ...] = (
    QuestionType.CONCEPT,
    QuestionType.CODING,
    QuestionType.EXPLAIN,
)


class PracticeTopic(BaseModel):
    skill_id: str
    name: str
    summary: str = ""
    counts: dict[str, int] = Field(
        default_factory=dict, description="How many questions of each kind the topic has."
    )


@functools.lru_cache(maxsize=4)
def _load(path: str) -> tuple[tuple[PracticeTopic, tuple[BankEntry, ...]], ...]:
    payload = yaml.safe_load(open(path, encoding="utf-8").read()) or {}
    topics: list[tuple[PracticeTopic, tuple[BankEntry, ...]]] = []
    for topic in payload.get("topics", []):
        entries: list[BankEntry] = []
        for row in topic.get("questions", []):
            kind = QuestionType(row["type"])
            if kind not in PRACTICE_KINDS:
                raise ValueError(f"{row['id']}: practice questions are concept, coding or explain")
            options = [str(option) for option in row.get("choices", [])]
            if kind is QuestionType.CONCEPT and len(set(options)) < 2:
                raise ValueError(f"{row['id']}: a multiple-choice question needs its choices")
            entries.append(
                BankEntry(
                    question=Question(
                        id=row["id"],
                        type=kind,
                        prompt=row["prompt"],
                        code_context=(row.get("code") or "").rstrip(),
                        skill_ids=[topic["skill_id"]],
                        level=int(row.get("level", 2)),
                        starter=row.get("starter", ""),
                        choices=_shuffled(row["id"], options) if kind is QuestionType.CONCEPT else [],
                    ),
                    key_points=[str(point) for point in row.get("key_points", [])],
                    solution=(row.get("solution") or "").strip(),
                    answer=options[0] if kind is QuestionType.CONCEPT else "",
                )
            )
        counts = {kind.value: sum(1 for e in entries if e.question.type is kind) for kind in PRACTICE_KINDS}
        topics.append(
            (
                PracticeTopic(
                    skill_id=topic["skill_id"],
                    name=topic["name"],
                    summary=topic.get("summary", ""),
                    counts=counts,
                ),
                tuple(entries),
            )
        )
    return tuple(topics)


def _bank(settings: Settings) -> tuple[tuple[PracticeTopic, tuple[BankEntry, ...]], ...]:
    return _load(str(settings.knowledge_data_dir / "practice_bank.yaml"))


def topics(settings: Settings) -> list[PracticeTopic]:
    return [topic for topic, _ in _bank(settings)]


def questions(settings: Settings, skill_id: str, kind: QuestionType | None = None) -> list[Question] | None:
    """The topic's questions, easiest first. None when there is no such topic."""
    for topic, entries in _bank(settings):
        if topic.skill_id == skill_id:
            chosen = [e.question for e in entries if kind is None or e.question.type is kind]
            return sorted(chosen, key=lambda question: question.level)
    return None


def entry_for(settings: Settings, question_id: str) -> BankEntry | None:
    return next(
        (entry for _, entries in _bank(settings) for entry in entries if entry.question.id == question_id),
        None,
    )
