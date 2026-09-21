"""The revision loop: questions, answers, grading."""

from enum import Enum

from pydantic import BaseModel, Field

from .common import Evidence
from .scores import Tier


class QuestionType(str, Enum):
    RECALL = "recall"
    JUSTIFY = "justify"
    TRANSFER = "transfer"
    DEBUG = "debug"
    EXTEND = "extend"
    # Seeded drills used by the adaptive loop. These are not derived from the
    # user's code, so they carry no target.
    CONCEPT = "concept"
    CODING = "coding"
    # Read a piece of code and say what it does and why. The code rides in
    # `code_context`; there is no target, because it is not the user's code.
    EXPLAIN = "explain"


# The five derived from the user's own code, in the order a session walks them.
# Seeded drill types are deliberately not here: they have no code target, and
# anything iterating "the question types" means these.
GENERATED_TYPES: tuple[QuestionType, ...] = (
    QuestionType.RECALL,
    QuestionType.JUSTIFY,
    QuestionType.TRANSFER,
    QuestionType.DEBUG,
    QuestionType.EXTEND,
)
SEEDED_TYPES: tuple[QuestionType, ...] = (
    QuestionType.CONCEPT,
    QuestionType.CODING,
    QuestionType.EXPLAIN,
)


class Question(BaseModel):
    id: str
    type: QuestionType
    target: Evidence | None = Field(
        None, description="The function this question is about. None for seeded drills."
    )
    target_name: str = ""
    prompt: str
    code_context: str = Field(
        "", description="Function + callees + creating commit diff, ~3k tokens"
    )
    skill_ids: list[str] = Field(default_factory=list)
    level: int = Field(
        2, ge=1, le=4, description="1 name it, 2 explain it, 3 reason about it, 4 design with it"
    )
    starter: str = Field("", description="Opening lines for a coding task.")
    choices: list[str] = Field(
        default_factory=list,
        description=(
            "Options for a multiple-choice concept drill, already shuffled. "
            "The submission is the chosen option's text. Empty for free-text and coding drills."
        ),
    )


class Answer(BaseModel):
    question_id: str
    submission: str


class GradeResult(BaseModel):
    question_id: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str
    tier_change: dict[str, Tier] = Field(
        default_factory=dict, description="skill_id -> new tier, when a promotion happened"
    )


class NextQuestion(BaseModel):
    """One step of the adaptive loop.

    `question` is None once every skill worth probing has been bracketed --
    that is the session ending, not an error.
    """

    question: Question | None = None
    asked: int = 0
    session_length: int = Field(5, description="How many questions one recall session asks.")
    remaining_skills: int = 0
    reason: str = Field("", description="Why this question was chosen, shown to the user.")


class PracticeGrade(BaseModel):
    """The result of one practice question. Practice never changes a tier or the roadmap."""

    question_id: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str
    missing: list[str] = Field(default_factory=list, description="Key points the answer did not make.")
    model_answer: str = ""


class AdaptiveGrade(GradeResult):
    """A grade plus the question the answer earned."""

    level: int = 2
    next_level: int | None = None
    model_answer: str = ""
    next: NextQuestion | None = None
