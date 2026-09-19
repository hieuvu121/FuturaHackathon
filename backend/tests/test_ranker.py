"""Tests for deterministic metadata-only scan ranking."""

from datetime import datetime, timezone

from app.schemas.repo_map import FunctionNode, RepoMap
from app.services.analyze.ranker import rank_files


def _function(
    file: str,
    name: str,
    *,
    complexity: int,
    times_modified: int,
    loc: int,
) -> FunctionNode:
    return FunctionNode(
        name=name,
        file=file,
        lines=(1, loc),
        complexity=complexity,
        loc=loc,
        times_modified=times_modified,
    )


def _repo_map(functions: list[FunctionNode]) -> RepoMap:
    return RepoMap(
        repo="developer/project",
        language="python",
        analyzed_at=datetime.now(timezone.utc),
        total_files=len({function.file for function in functions}),
        functions=functions,
    )


def test_ranks_files_by_aggregate_complexity_churn_and_size():
    repo_map = _repo_map(
        [
            _function("large.py", "one", complexity=5, times_modified=4, loc=20),
            _function("large.py", "two", complexity=5, times_modified=4, loc=20),
            _function("complex.py", "one", complexity=12, times_modified=5, loc=20),
            _function("small.py", "one", complexity=2, times_modified=2, loc=10),
        ]
    )

    # large.py: (5+5) * (4+4) * (20+20) = 3200
    # complex.py: 12 * 5 * 20 = 1200
    assert rank_files(repo_map) == ["large.py", "complex.py", "small.py"]


def test_applies_limit_after_grouping_functions_by_file():
    repo_map = _repo_map(
        [
            _function("a.py", "one", complexity=3, times_modified=3, loc=10),
            _function("a.py", "two", complexity=3, times_modified=3, loc=10),
            _function("b.py", "one", complexity=5, times_modified=5, loc=10),
        ]
    )

    assert rank_files(repo_map, limit=1) == ["a.py"]
    assert rank_files(repo_map, limit=0) == []
    assert rank_files(repo_map, limit=-1) == []


def test_breaks_equal_scores_by_path_for_deterministic_output():
    repo_map = _repo_map(
        [
            _function("z.py", "one", complexity=3, times_modified=3, loc=10),
            _function("a.py", "one", complexity=3, times_modified=3, loc=10),
        ]
    )

    assert rank_files(repo_map) == ["a.py", "z.py"]


def test_handles_an_empty_repo_map():
    assert rank_files(_repo_map([])) == []
