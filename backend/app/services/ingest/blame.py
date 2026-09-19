"""Optional git blame -> author_ratio. Owner: Track A.

Defaults to 1.0 for every function when settings.enable_blame is False.
"""

from pathlib import Path

from ...schemas.repo_map import FunctionNode


def enrich(root: Path, functions: list[FunctionNode], author_email: str) -> list[FunctionNode]:
    raise NotImplementedError
