"""Real-repository tests for commit history and optional blame enrichment."""

from datetime import datetime
import os
from pathlib import Path
import subprocess

import pytest

from app.services.ingest import blame, gitlog
from app.services.ingest.parser import parse_file


def _git(root: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def _commit(root: Path, message: str, date: str, name: str, email: str) -> str:
    _git(root, "add", "-A")
    commit_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_COMMITTER_DATE": date,
    }
    _git(root, "commit", "-q", "-m", message, env=commit_env)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def history_repo(tmp_path: Path) -> tuple[Path, str, str]:
    _git(tmp_path, "init", "-q")
    source = tmp_path / "old_name.py"
    source.write_text("def calculate(value):\n    return value + 1\n", encoding="utf-8")
    first = _commit(
        tmp_path,
        "feat: add calculation",
        "2025-01-01T10:00:00+00:00",
        "Alice",
        "alice@example.com",
    )

    source.write_text(
        "def calculate(value):\n    adjusted = value + 1\n    return adjusted\n",
        encoding="utf-8",
    )
    _commit(
        tmp_path,
        "refactor: make calculation explicit",
        "2025-01-08T10:00:00+00:00",
        "Bob",
        "bob@example.com",
    )

    _git(tmp_path, "mv", "old_name.py", "calculate.py")
    last = _commit(
        tmp_path,
        "chore: rename calculation module",
        "2025-01-15T10:00:00+00:00",
        "Bob",
        "bob@example.com",
    )
    return tmp_path, first, last


def test_enrich_follows_renames_and_attaches_file_history(history_repo):
    root, first, _ = history_repo
    functions = parse_file(root, "calculate.py")

    enriched = gitlog.enrich(root, functions)

    assert enriched[0].times_modified == 3
    assert enriched[0].last_modified == datetime.fromisoformat("2025-01-15T10:00:00+00:00")
    assert enriched[0].created_commit == first


def test_commit_stats_report_size_cadence_refactors_and_hotspots(history_repo):
    root, _, _ = history_repo

    stats = gitlog.commit_stats(root)

    assert stats["commits_analyzed"] == 3
    assert stats["median_commit_size"] == 2
    # Both the explicit refactor and isolated rename are refactoring commits.
    assert stats["refactor_ratio"] == pytest.approx(2 / 3, abs=0.0001)
    assert stats["median_days_between_commits"] == 7.0
    assert stats["hotspots"][0]["churn"] >= 2


def test_blame_computes_function_line_share_for_author(history_repo):
    root, _, _ = history_repo
    functions = parse_file(root, "calculate.py")

    blame.enrich(root, functions, "ALICE@example.com")

    assert functions[0].author_ratio == pytest.approx(1 / 3, abs=0.0001)


def test_blame_stays_at_safe_default_when_disabled(history_repo):
    root, _, _ = history_repo
    functions = parse_file(root, "calculate.py")

    blame.enrich(root, functions, "")

    assert functions[0].author_ratio == 1.0


def test_git_history_rejects_path_traversal(history_repo):
    root, _, _ = history_repo
    functions = parse_file(root, "calculate.py")
    functions[0].file = "../outside.py"

    with pytest.raises(ValueError, match="escapes"):
        gitlog.enrich(root, functions)


def test_commit_stats_support_empty_repository(tmp_path: Path):
    _git(tmp_path, "init", "-q")

    stats = gitlog.commit_stats(tmp_path)

    assert stats["commits_analyzed"] == 0
    assert stats["hotspots"] == []
