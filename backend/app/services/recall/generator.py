"""Five question types from one target. Owner: Track B.

Types: recall, justify, transfer, debug, extend.
Reference answers come from knowledge_data/questions.yaml.
Code context = the function + its callees + the creating commit diff (~3k tokens).
"""

from pathlib import Path

from ...config import Settings
from ...schemas.recall import Question
from ...schemas.repo_map import FunctionNode, RepoMap


def build_context(root: Path, repo_map: RepoMap, target: FunctionNode) -> str:
    """Function source + callee sources + `git show` of created_commit."""
    raise NotImplementedError


def generate(settings: Settings, root: Path, repo_map: RepoMap, targets: list[FunctionNode]) -> list[Question]:
    raise NotImplementedError
