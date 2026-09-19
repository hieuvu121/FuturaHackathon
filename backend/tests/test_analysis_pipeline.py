"""Integration tests for the non-persistent analysis orchestration."""

from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.schemas.findings import Finding
from app.schemas.repo_map import FunctionNode, RepoMap
from app.services import analyze


def _finding(finding_id: str, file: str, lines: tuple[int, int]) -> Finding:
    return Finding.model_validate(
        {
            "id": finding_id,
            "dimension": "code_structure",
            "severity": "medium",
            "observation": "A grounded architecture observation.",
            "evidence": {"file": file, "lines": lines},
            "confidence": 0.9,
        }
    )


def _repo_map() -> RepoMap:
    return RepoMap(
        repo="owner/project",
        language="python",
        analyzed_at=datetime.now(UTC),
        total_files=2,
        functions=[
            FunctionNode(
                name="simple",
                file="simple.py",
                lines=(1, 2),
                complexity=1,
                loc=2,
                times_modified=1,
            ),
            FunctionNode(
                name="complex_handler",
                file="complex.py",
                lines=(1, 6),
                complexity=5,
                nesting_depth=2,
                loc=6,
                times_modified=3,
            ),
        ],
    )


def test_analysis_pipeline_ranks_scans_validates_and_scores(tmp_path: Path, monkeypatch):
    settings = Settings(cache_dir=tmp_path / "cache", scan_file_limit=1)
    root = analyze.clone_service.cache_path(settings, "developer", "owner/project")
    root.mkdir(parents=True)
    (root / "simple.py").write_text("def simple():\n    return 1\n", encoding="utf-8")
    (root / "complex.py").write_text(
        "def complex_handler(value):\n"
        "    if value:\n"
        "        try:\n"
        "            return value\n"
        "        except Exception:\n"
        "            pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(analyze, "build_repo_map", lambda *args, **kwargs: _repo_map())
    monkeypatch.setattr(
        analyze.gitlog,
        "commit_stats",
        lambda root: {
            "commits_analyzed": 4,
            "median_commit_size": 100,
            "refactor_ratio": 0.1,
        },
    )
    scanned: list[str] = []

    def fake_scan(settings, root, rel_path):
        scanned.append(rel_path)
        return [
            _finding("grounded", rel_path, (1, 2)),
            _finding("past-eof", rel_path, (1, 99)),
        ]

    monkeypatch.setattr(analyze, "scan_file", fake_scan)

    result = analyze.analyze_repository(
        settings,
        "developer",
        "owner/project",
        "github-token",
    )

    assert scanned == ["complex.py"]
    assert [finding.id for finding in result.findings] == ["grounded"]
    assert [finding.id for finding in result.dropped_findings] == ["past-eof"]
    assert result.repository_metrics["empty_catch_count"] == 1
    assert result.repository_metrics["swallowed_exception_count"] == 1
    assert result.repository_metrics["hardcoded_secret_count"] == 0
    assert result.scores.repo == "owner/project"
    code_structure = next(
        dimension
        for dimension in result.scores.dimensions
        if dimension.dimension == "code_structure"
    )
    assert code_structure.evidence == [result.findings[0].evidence]


def test_analysis_pipeline_handles_an_empty_scan_set(tmp_path: Path, monkeypatch):
    settings = Settings(cache_dir=tmp_path / "cache", scan_file_limit=0)
    root = analyze.clone_service.cache_path(settings, "developer", "owner/project")
    root.mkdir(parents=True)
    monkeypatch.setattr(
        analyze,
        "build_repo_map",
        lambda *args, **kwargs: RepoMap(
            repo="owner/project",
            language="python",
            analyzed_at=datetime.now(UTC),
            total_files=0,
        ),
    )
    monkeypatch.setattr(analyze.gitlog, "commit_stats", lambda root: {})

    result = analyze.analyze_repository(settings, "developer", "owner/project", "")

    assert result.findings == []
    assert result.dropped_findings == []
    assert result.scores.repo == "owner/project"
