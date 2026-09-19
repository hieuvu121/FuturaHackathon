"""Deterministic commit-history metrics. Owner: Track A.

Derives per-file churn, hotspots, commit size and cadence, refactor-vs-append
behaviour, and attaches times_modified / last_modified / created_commit.
"""

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import re
from statistics import median
import subprocess

from ...schemas.repo_map import FunctionNode

COMMIT_MARKER = "commit\x1f"
REFACTOR_SUBJECT = re.compile(
    r"\b(?:refactor|restructure|cleanup|clean[ -]?up|simplif\w*|extract|rename|move)\b",
    re.IGNORECASE,
)


class GitHistoryError(RuntimeError):
    """Raised when repository history cannot be read."""


def _git(root: Path, *arguments: str) -> str:
    root = root.resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitHistoryError("Git executable is not available") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "unknown Git error"
        raise GitHistoryError(detail) from exc
    return result.stdout


def _safe_relative_path(root: Path, rel_path: str) -> str:
    root = root.resolve()
    candidate = (root / rel_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Source path escapes repository root: {rel_path}")
    return candidate.relative_to(root).as_posix()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _file_history(root: Path, rel_path: str) -> list[tuple[str, datetime]]:
    output = _git(root, "log", "--follow", "--format=%H%x1f%cI", "--", rel_path)
    history: list[tuple[str, datetime]] = []
    for line in output.splitlines():
        if "\x1f" not in line:
            continue
        commit, committed_at = line.split("\x1f", 1)
        history.append((commit, _parse_datetime(committed_at)))
    return history


def enrich(root: Path, functions: list[FunctionNode]) -> list[FunctionNode]:
    """Attach file-level history to every current function."""
    histories: dict[str, list[tuple[str, datetime]]] = {}
    for function in functions:
        rel_path = _safe_relative_path(root, function.file)
        if rel_path not in histories:
            histories[rel_path] = _file_history(root, rel_path)

        history = histories[rel_path]
        if not history:
            continue
        function.times_modified = len(history)
        function.last_modified = history[0][1]
        function.created_commit = history[-1][0]
    return functions


def _commits(root: Path) -> list[dict]:
    try:
        output = _git(
            root,
            "log",
            "--format=commit%x1f%H%x1f%cI%x1f%s",
            "--numstat",
        )
    except GitHistoryError:
        if _git(root, "rev-parse", "--is-inside-work-tree").strip() == "true":
            return []
        raise
    commits: list[dict] = []
    current: dict | None = None
    for line in output.splitlines():
        if line.startswith(COMMIT_MARKER):
            _, commit, committed_at, subject = line.split("\x1f", 3)
            current = {
                "commit": commit,
                "committed_at": _parse_datetime(committed_at),
                "subject": subject,
                "additions": 0,
                "deletions": 0,
                "files": {},
            }
            commits.append(current)
            continue
        if current is None or not line or "\t" not in line:
            continue
        added, deleted, path = line.split("\t", 2)
        if not added.isdigit() or not deleted.isdigit():
            continue
        additions, deletions = int(added), int(deleted)
        current["additions"] += additions
        current["deletions"] += deletions
        current["files"][path] = additions + deletions
    return commits


def commit_stats(root: Path) -> dict:
    """Return cadence, commit-size, refactor, and hotspot metrics."""
    commits = _commits(root)
    if not commits:
        return {
            "commits_analyzed": 0,
            "median_commit_size": 0,
            "refactor_ratio": 0.0,
            "commits_per_week": 0.0,
            "median_days_between_commits": None,
            "file_churn": {},
            "hotspots": [],
        }

    sizes = [commit["additions"] + commit["deletions"] for commit in commits]
    refactors = sum(bool(REFACTOR_SUBJECT.search(commit["subject"])) for commit in commits)
    dates = sorted(commit["committed_at"] for commit in commits)
    intervals = [
        (current - previous).total_seconds() / 86_400
        for previous, current in zip(dates, dates[1:])
    ]
    span_days = max((dates[-1] - dates[0]).total_seconds() / 86_400, 1.0)

    file_churn: dict[str, int] = defaultdict(int)
    for commit in commits:
        for path, churn in commit["files"].items():
            file_churn[path] += churn
    ordered_churn = dict(sorted(file_churn.items(), key=lambda item: (-item[1], item[0])))

    return {
        "commits_analyzed": len(commits),
        "median_commit_size": median(sizes),
        "refactor_ratio": round(refactors / len(commits), 4),
        "commits_per_week": round(len(commits) / max(span_days / 7, 1.0), 2),
        "median_days_between_commits": round(median(intervals), 2) if intervals else None,
        "file_churn": ordered_churn,
        "hotspots": [
            {"file": path, "churn": churn}
            for path, churn in list(ordered_churn.items())[:10]
        ],
    }
