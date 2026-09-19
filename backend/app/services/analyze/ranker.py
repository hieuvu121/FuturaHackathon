"""Orders files by complexity x churn x size. Owner: Track B.

repo_map metadata only. NO model calls in this file.
"""

from ...schemas.repo_map import RepoMap


def rank_files(repo_map: RepoMap, limit: int = 25) -> list[str]:
    """Returns the top `limit` file paths as the scan set."""
    raise NotImplementedError
