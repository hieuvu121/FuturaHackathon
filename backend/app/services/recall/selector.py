"""Picks recall targets from repo_map. Owner: Track B.

Filter (OVERALL.md section 1):
    last_modified 1-3 months ago
    AND complexity high
    AND has_test == False
    AND author_ratio > threshold
    AND prefer functions carrying high-severity findings
-> 5 targets, ranked.
"""

from ...schemas.findings import Finding
from ...schemas.repo_map import FunctionNode, RepoMap


def select_targets(
    repo_map: RepoMap, findings: list[Finding], limit: int = 5, author_ratio_min: float = 0.5
) -> list[FunctionNode]:
    raise NotImplementedError
