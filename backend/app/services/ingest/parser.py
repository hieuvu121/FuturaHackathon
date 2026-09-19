"""tree-sitter extraction. Owner: Track A.

Runs over kept files for the target language, extracting every function and
class with its file and line range. No metrics here -- that is metrics.py.
"""

from pathlib import Path

from ...schemas.repo_map import FunctionNode


def parse_file(root: Path, rel_path: str) -> list[FunctionNode]:
    """One file -> its functions, with name/file/lines/loc filled in."""
    raise NotImplementedError
