"""Bug injection is accepted only when a real test catches it."""

from pathlib import Path

import pytest

from app.config import Settings
from app.schemas.repo_map import FunctionNode
from app.services.recall import injector


def _target() -> FunctionNode:
    return FunctionNode(
        name="add",
        file="maths.py",
        lines=(1, 2),
        complexity=1,
        loc=2,
        has_test=True,
    )


def test_injector_runs_tests_and_retries_until_bug_is_caught(tmp_path: Path, monkeypatch):
    original = "def add(left, right):\n    return left + right"
    (tmp_path / "maths.py").write_text(original + "\n", encoding="utf-8")
    (tmp_path / "test_maths.py").write_text(
        "from maths import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    attempts = []

    def candidate(settings, target, source, attempt):
        attempts.append(attempt)
        broken = original if attempt == 1 else "def add(left, right):\n    return left - right"
        return injector.InjectionCandidate(broken_code=broken, fix=original)

    monkeypatch.setattr(injector, "_candidate", candidate)

    result = injector.inject_bug(Settings(), tmp_path, _target())

    assert attempts == [1, 2]
    assert "1 failed" in result["failing_test"]
    assert "return left - right" in result["broken_code"]
    assert (tmp_path / "maths.py").read_text(encoding="utf-8") == original + "\n"


def test_injector_requires_tests(tmp_path: Path):
    target = _target()
    target.has_test = False
    with pytest.raises(injector.InjectionError, match="existing tests"):
        injector.inject_bug(Settings(), tmp_path, target)
