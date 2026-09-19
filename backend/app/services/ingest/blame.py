"""Optional git blame -> author_ratio. Owner: Track A.

Defaults to 1.0 for every function when settings.enable_blame is False.
"""

from collections import defaultdict
from pathlib import Path
import re

from ...schemas.repo_map import FunctionNode
from .gitlog import GitHistoryError, _git, _safe_relative_path

BLAME_HEADER = re.compile(r"^\^?[0-9a-f]{40,64} \d+ (\d+)(?: \d+)?$")


def _normalise_email(value: str) -> str:
    return value.strip().removeprefix("<").removesuffix(">").casefold()


def _line_authors(root: Path, rel_path: str) -> dict[int, str]:
    output = _git(root, "blame", "--line-porcelain", "--", rel_path)
    authors: dict[int, str] = {}
    current_line: int | None = None
    for line in output.splitlines():
        header = BLAME_HEADER.match(line)
        if header:
            current_line = int(header.group(1))
        elif line.startswith("author-mail ") and current_line is not None:
            authors[current_line] = _normalise_email(line.removeprefix("author-mail "))
    return authors


def enrich(root: Path, functions: list[FunctionNode], author_email: str) -> list[FunctionNode]:
    """Compute the share of each function's current lines owned by the user."""
    target = _normalise_email(author_email)
    if not target:
        return functions

    by_file: dict[str, list[FunctionNode]] = defaultdict(list)
    for function in functions:
        by_file[_safe_relative_path(root, function.file)].append(function)

    for rel_path, file_functions in by_file.items():
        try:
            authors = _line_authors(root, rel_path)
        except GitHistoryError:
            continue
        for function in file_functions:
            start, end = function.lines
            owned = sum(authors.get(line) == target for line in range(start, end + 1))
            attributed = sum(line in authors for line in range(start, end + 1))
            if attributed:
                function.author_ratio = round(owned / attributed, 4)
    return functions
