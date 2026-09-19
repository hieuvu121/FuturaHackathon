"""The adaptive drill loop. Owner: Track B.

Recall exists to find gaps, not to award a score, so the loop is a search
rather than a quiz. Each answer decides the next question:

    start a skill at level 2
    passed  -> ask one level harder
    failed  -> ask one level easier

A skill is done once it has been *bracketed* -- a pass at one level and a
failure at the next -- because that pair is the gap, and asking further
questions about it tells us nothing new. Bottoming out (failed the easiest
question the bank holds) or topping out (passed the hardest) brackets it too.
The loop then moves to the next skill, which is why a session converges on
weak spots instead of grinding through a fixed list.

Skills are drawn in the roadmap's own order: what the user has written but
never had checked comes first, since that is where an unfounded belief is
most likely hiding. Questions come from knowledge_data/recall_bank.yaml, so
a demo never waits on a model.
"""

from dataclasses import dataclass
import functools
import hashlib
from pathlib import Path

import yaml

from ...config import Settings
from ...schemas.recall import NextQuestion, Question, QuestionType

START_LEVEL = 2
MIN_LEVEL = 1
MAX_LEVEL = 4


@dataclass(frozen=True)
class Attempt:
    """One graded answer, in the order it happened."""

    skill_id: str
    level: int
    passed: bool
    question_id: str


@dataclass(frozen=True)
class BankEntry:
    question: Question
    key_points: list[str]
    solution: str
    # The correct option of a multiple-choice drill. Kept here, beside the key
    # points, because like them it must never reach the browser.
    answer: str = ""


def _shuffled(question_id: str, options: list[str]) -> list[str]:
    """A fixed order per question: stable across refreshes, unrelated to the file's order."""
    return sorted(
        options, key=lambda option: hashlib.sha1(f"{question_id}|{option}".encode()).hexdigest()
    )


def _load_choices(bank_path: str) -> dict[str, list[str]]:
    """question id -> options, correct one first. See knowledge_data/recall_choices.yaml."""
    path = Path(bank_path).with_name("recall_choices.yaml")
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        question_id: [str(option) for option in options]
        for question_id, options in (payload.get("choices") or {}).items()
        if isinstance(options, list) and len(set(options)) >= 2
    }


@functools.lru_cache(maxsize=4)
def _load(path: str) -> tuple[BankEntry, ...]:
    payload = yaml.safe_load(open(path, encoding="utf-8").read()) or {}
    choices = _load_choices(path)
    entries: list[BankEntry] = []
    for row in payload.get("questions", []):
        # Only theory questions become multiple choice; a coding task is written, not picked.
        options = choices.get(row["id"], []) if row["type"] == QuestionType.CONCEPT.value else []
        entries.append(
            BankEntry(
                question=Question(
                    id=row["id"],
                    type=QuestionType(row["type"]),
                    prompt=row["prompt"],
                    skill_ids=[row["skill_id"]],
                    level=int(row["level"]),
                    starter=row.get("starter", ""),
                    choices=_shuffled(row["id"], options),
                ),
                key_points=[str(point) for point in row.get("key_points", [])],
                solution=(row.get("solution") or "").strip(),
                answer=options[0] if options else "",
            )
        )
    return tuple(entries)


def load_bank(settings: Settings) -> tuple[BankEntry, ...]:
    return _load(str(settings.knowledge_data_dir / "recall_bank.yaml"))


def entry_for(settings: Settings, question_id: str) -> BankEntry | None:
    return next((e for e in load_bank(settings) if e.question.id == question_id), None)


def _skill_of(entry: BankEntry) -> str:
    return entry.question.skill_ids[0]


def _levels_available(
    bank: tuple[BankEntry, ...], skill_id: str, prefer: QuestionType | None = None
) -> dict[int, BankEntry]:
    """One drill per level for this skill.

    Later entries win a level, which is how a repository drill displaces a
    seeded one. When the session wants a particular kind of question next, a
    drill of that kind holds its level against a later one of another kind.
    """
    chosen: dict[int, BankEntry] = {}
    for entry in bank:
        if _skill_of(entry) != skill_id:
            continue
        held = chosen.get(entry.question.level)
        if held is None or prefer is None or entry.question.type is prefer or held.question.type is not prefer:
            chosen[entry.question.level] = entry
    return chosen


def _of_kind(
    available: dict[int, BankEntry], level: int, prefer: QuestionType | None, asked_ids: set[str]
) -> int:
    """The level to ask at. If the wanted level has the wrong kind of question,
    one step either side is close enough to keep the mix the session promised."""
    if prefer is None or available[level].question.type is prefer:
        return level
    for nearby in (level + 1, level - 1):
        entry = available.get(nearby)
        if entry is not None and entry.question.type is prefer and entry.question.id not in asked_ids:
            return nearby
    return level


def is_bracketed(attempts: list[Attempt], skill_id: str, available: dict[int, BankEntry]) -> bool:
    """True once further questions about this skill would tell us nothing new."""
    rows = [a for a in attempts if a.skill_id == skill_id]
    if not rows:
        return False
    passed = {a.level for a in rows if a.passed}
    failed = {a.level for a in rows if not a.passed}

    # The gap itself: cleared one level, missed the next.
    if any(level + 1 in failed for level in passed):
        return True
    # Topped out or bottomed out among the levels that actually exist for this
    # skill. Bounding by the bank rather than by 1..4 matters: passing the
    # hardest question there is tells us everything an easier one would, so
    # asking it anyway would waste the user's time.
    if available:
        if max(available) in passed:
            return True
        if min(available) in failed:
            return True
    if MIN_LEVEL in failed or MAX_LEVEL in passed:
        return True
    # Ran out of questions to ask about it.
    return {a.level for a in rows} >= set(available)


def _next_level(attempts: list[Attempt], skill_id: str, available: dict[int, BankEntry]) -> int | None:
    """Where to probe next within one skill, or None when it is exhausted."""
    rows = [a for a in attempts if a.skill_id == skill_id]
    if not rows:
        return START_LEVEL if START_LEVEL in available else min(available, default=None)

    last = rows[-1]
    wanted = last.level + 1 if last.passed else last.level - 1
    asked = {a.level for a in rows}

    # Walk outward in the direction the last answer pointed, then settle for
    # any level we have not asked yet.
    step = 1 if last.passed else -1
    level = wanted
    while MIN_LEVEL <= level <= MAX_LEVEL:
        if level in available and level not in asked:
            return level
        level += step
    remaining = sorted(set(available) - asked)
    return remaining[0] if remaining else None


def _reason(attempts: list[Attempt], skill_id: str, level: int, skill_name: str) -> str:
    rows = [a for a in attempts if a.skill_id == skill_id]
    if not rows:
        return f"Starting {skill_name} in the middle to find your level."
    last = rows[-1]
    if last.passed:
        return f"You cleared level {last.level}, so here is a harder {skill_name} question."
    return f"Level {last.level} did not land, so here is an easier {skill_name} one."


def next_question(
    settings: Settings,
    attempts: list[Attempt],
    skill_order: list[tuple[str, str]],
    extra: tuple[BankEntry, ...] = (),
    prefer: QuestionType | None = None,
) -> NextQuestion:
    """Pick the next drill.

    `skill_order` is (skill_id, display name) in the priority the roadmap gives
    them. Skills with no seeded questions are skipped rather than reported as
    finished, so the bank can grow without changing this code.

    `extra` holds drills written against the user's own repository
    (repo_drills.py). They take the place of the seeded question at the same
    skill and level, so the loop probes real code wherever it has some.

    `prefer` is the kind of question the session would like next -- a coding
    task or a multiple-choice one. It is honoured where the bank allows and
    ignored where it does not: the level search always comes first.
    """
    bank = (*load_bank(settings), *extra)
    asked_ids = {a.question_id for a in attempts}

    open_skills: list[tuple[str, str, dict[int, BankEntry]]] = []
    for skill_id, skill_name in skill_order:
        available = _levels_available(bank, skill_id, prefer)
        if not available or is_bracketed(attempts, skill_id, available):
            continue
        open_skills.append((skill_id, skill_name, available))

    if not open_skills:
        return NextQuestion(question=None, asked=len(attempts), remaining_skills=0)

    # Finish the skill already in flight before starting another one.
    in_flight = next(
        (row for row in open_skills if any(a.skill_id == row[0] for a in attempts)), None
    )
    skill_id, skill_name, available = in_flight or open_skills[0]

    level = _next_level(attempts, skill_id, available)
    while level is None or available[level].question.id in asked_ids:
        open_skills = [row for row in open_skills if row[0] != skill_id]
        if not open_skills:
            return NextQuestion(question=None, asked=len(attempts), remaining_skills=0)
        skill_id, skill_name, available = open_skills[0]
        level = _next_level(attempts, skill_id, available)

    level = _of_kind(available, level, prefer, asked_ids)
    if prefer is not None and available[level].question.type is not prefer:
        # This skill cannot supply the kind of question the session wants next.
        # Another open skill may: the loop's state is read from the attempt log,
        # so stepping away and coming back later loses nothing.
        for other_id, other_name, other_available in open_skills:
            if other_id == skill_id:
                continue
            other_level = _next_level(attempts, other_id, other_available)
            if other_level is None:
                continue
            other_level = _of_kind(other_available, other_level, prefer, asked_ids)
            entry = other_available[other_level]
            if entry.question.type is prefer and entry.question.id not in asked_ids:
                skill_id, skill_name, available, level = other_id, other_name, other_available, other_level
                break

    return NextQuestion(
        question=available[level].question,
        asked=len(attempts),
        remaining_skills=len(open_skills),
        reason=_reason(attempts, skill_id, level, skill_name),
    )
