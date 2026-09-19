"""Tests for the finding validator's evidence boundary."""

import logging
from pathlib import Path

import pytest

from app.schemas.findings import Finding
from app.services.analyze.validator import validate


def _finding(finding_id: str, file: str, lines: tuple[int, int]) -> Finding:
    return Finding.model_validate(
        {
            "id": finding_id,
            "dimension": "code_structure",
            "severity": "medium",
            "observation": "An observation grounded in the cited source range.",
            "evidence": {"file": file, "lines": lines, "commit": "abc123"},
            "confidence": 0.9,
        }
    )


def test_keeps_resolvable_inclusive_line_ranges(tmp_path: Path):
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir()
    source.write_text("first\nsecond\nthird", encoding="utf-8")
    findings = [
        _finding("first-line", "src/example.py", (1, 1)),
        _finding("last-line", "src/example.py", (3, 3)),
        _finding("whole-file", "src/example.py", (1, 3)),
    ]

    kept, dropped = validate(tmp_path, findings)

    assert kept == findings
    assert dropped == []


@pytest.mark.parametrize(
    ("finding_id", "file", "lines"),
    [
        ("missing", "src/missing.py", (1, 1)),
        ("directory", "src", (1, 1)),
        ("zero-based", "src/example.py", (0, 1)),
        ("reversed", "src/example.py", (2, 1)),
        ("past-eof", "src/example.py", (1, 3)),
    ],
)
def test_drops_unresolvable_evidence(
    tmp_path: Path, finding_id: str, file: str, lines: tuple[int, int]
):
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir()
    source.write_text("first\nsecond\n", encoding="utf-8")
    finding = _finding(finding_id, file, lines)

    kept, dropped = validate(tmp_path, [finding])

    assert kept == []
    assert dropped == [finding]


def test_drops_paths_outside_the_repository(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret\n", encoding="utf-8")
    findings = [
        _finding("traversal", "../outside.py", (1, 1)),
        _finding("absolute", str(outside), (1, 1)),
    ]

    kept, dropped = validate(root, findings)

    assert kept == []
    assert dropped == findings


def test_drops_symlinks_that_escape_the_repository(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret\n", encoding="utf-8")
    link = root / "linked.py"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")
    finding = _finding("symlink", "linked.py", (1, 1))

    kept, dropped = validate(root, [finding])

    assert kept == []
    assert dropped == [finding]


def test_preserves_input_order_and_logs_dropped_findings(tmp_path: Path, caplog):
    source = tmp_path / "example.py"
    source.write_text("one line\n", encoding="utf-8")
    findings = [
        _finding("kept-1", "example.py", (1, 1)),
        _finding("dropped-1", "missing.py", (1, 1)),
        _finding("kept-2", "example.py", (1, 1)),
        _finding("dropped-2", "example.py", (1, 2)),
    ]

    with caplog.at_level(logging.WARNING, logger="app.services.analyze.validator"):
        kept, dropped = validate(tmp_path, findings)

    assert [finding.id for finding in kept] == ["kept-1", "kept-2"]
    assert [finding.id for finding in dropped] == ["dropped-1", "dropped-2"]
    assert "Dropped finding dropped-1" in caplog.text
    assert "Dropped finding dropped-2" in caplog.text
