"""Five question types from one target. Owner: Track B.

Types: recall, justify, transfer, debug, extend.
Reference answers come from knowledge_data/questions.yaml.
Code context = the function + its callees + the creating commit diff (~3k tokens).
"""

import hashlib
from pathlib import Path

import yaml

from ...config import Settings
from ...schemas.recall import Question
from ...schemas.recall import QuestionType
from ...schemas.repo_map import FunctionNode, RepoMap
from ..ingest.gitlog import GitHistoryError, _git
from ..knowledge import get_taxonomy

QUESTION_ORDER = list(QuestionType)
MAX_CONTEXT_CHARS = 12_000


def _source_slice(root: Path, function: FunctionNode) -> str:
    root = root.resolve()
    path = (root / function.file).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Function source is outside the repository: {function.file}")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start, end = function.lines
    if start < 1 or end < start or end > len(lines):
        raise ValueError(f"Function range is invalid: {function.qualified_name}")
    return "\n".join(lines[start - 1 : end])


def build_context(root: Path, repo_map: RepoMap, target: FunctionNode) -> str:
    """Function source + callee sources + `git show` of created_commit."""
    sections = [f"# Target: {target.qualified_name}\n{_source_slice(root, target)}"]
    called = set(target.calls)
    callees = [
        function
        for function in repo_map.functions
        if function is not target and function.name.rsplit(".", 1)[-1] in called
    ]
    for callee in sorted(callees, key=lambda item: item.qualified_name):
        sections.append(f"# Callee: {callee.qualified_name}\n{_source_slice(root, callee)}")
    if target.created_commit:
        try:
            diff = _git(
                root,
                "show",
                "--format=",
                "--find-renames",
                "--unified=20",
                target.created_commit,
                "--",
                target.file,
            ).strip()
        except GitHistoryError:
            diff = ""
        if diff:
            sections.append(f"# Creating commit diff\n{diff}")
    return "\n\n".join(sections)[:MAX_CONTEXT_CHARS]


def generate(
    settings: Settings,
    root: Path,
    repo_map: RepoMap,
    targets: list[FunctionNode],
    question_types: list[QuestionType] | None = None,
) -> list[Question]:
    payload = yaml.safe_load(
        (settings.knowledge_data_dir / "questions.yaml").read_text(encoding="utf-8")
    )["question_types"]
    taxonomy = get_taxonomy(settings)
    language_skill = taxonomy.normalise(repo_map.language)
    questions: list[Question] = []
    for question_type, target in zip(question_types or QUESTION_ORDER, targets[:5]):
        context = build_context(root, repo_map, target)
        prompt = payload[question_type.value]["template"].format(
            function_name=target.name,
            file=target.file,
            code_context=context,
            extension_requirement="one additional validated input case",
        ).strip()
        digest = hashlib.sha256(
            f"{repo_map.repo}:{target.qualified_name}:{question_type.value}".encode()
        ).hexdigest()[:12]
        skills = [language_skill] if language_skill else []
        if question_type in {QuestionType.DEBUG, QuestionType.EXTEND}:
            testing_skill = taxonomy.normalise("unit testing")
            if testing_skill and testing_skill not in skills:
                skills.append(testing_skill)
        questions.append(
            Question(
                id=f"q-{digest}",
                type=question_type,
                target={
                    "file": target.file,
                    "lines": target.lines,
                    "commit": target.created_commit,
                },
                target_name=target.name,
                prompt=prompt,
                code_context=context,
                skill_ids=skills,
            )
        )
    return questions
