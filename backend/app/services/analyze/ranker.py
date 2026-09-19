"""Orders files by complexity x churn x size. Owner: Track B.

repo_map metadata only. NO model calls in this file.
"""

from collections import defaultdict

from ...schemas.repo_map import RepoMap


def rank_files(repo_map: RepoMap, limit: int = 25) -> list[str]:
    """Returns the top `limit` file paths as the scan set."""
    if limit <= 0:
        return []

    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"complexity": 0, "churn": 0, "loc": 0}
    )
    for function in repo_map.functions:
        metrics = totals[function.file]
        metrics["complexity"] += function.complexity
        metrics["churn"] += function.times_modified
        metrics["loc"] += function.loc

    def score(file: str) -> int:
        metrics = totals[file]
        return metrics["complexity"] * metrics["churn"] * metrics["loc"]

    ranked = sorted(totals, key=lambda file: (-score(file), file))
    return ranked[:limit]
