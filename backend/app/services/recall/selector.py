"""Picks recall targets from repo_map. Owner: Track B.

Filter (OVERALL.md section 1):
    last_modified 1-3 months ago
    AND complexity high
    AND has_test == False
    AND author_ratio > threshold
    AND prefer functions carrying high-severity findings
-> 5 targets, ranked.
"""

from datetime import UTC, datetime, timedelta

from ...schemas.findings import Finding
from ...schemas.repo_map import FunctionNode, RepoMap


def select_targets(
    repo_map: RepoMap,
    findings: list[Finding],
    limit: int = 5,
    author_ratio_min: float = 0.5,
    now: datetime | None = None,
) -> list[FunctionNode]:
    if limit <= 0:
        return []
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    newest = now - timedelta(days=30)
    oldest = now - timedelta(days=90)
    severe = {
        (finding.evidence.file, finding.evidence.lines)
        for finding in findings
        if finding.severity.value == "high"
    }

    eligible: list[FunctionNode] = []
    for function in repo_map.functions:
        modified = function.last_modified
        if modified is None:
            continue
        if modified.tzinfo is None:
            modified = modified.replace(tzinfo=UTC)
        if not (
            oldest <= modified <= newest
            and function.complexity >= 10
            and not function.has_test
            and function.author_ratio > author_ratio_min
        ):
            continue
        eligible.append(function)

    return sorted(
        eligible,
        key=lambda function: (
            -int((function.file, function.lines) in severe),
            -function.complexity,
            -function.author_ratio,
            function.file,
            function.lines,
            function.name,
        ),
    )[:limit]
