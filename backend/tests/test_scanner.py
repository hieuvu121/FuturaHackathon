"""LLM scanner boundary tests; no external model calls."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.services.analyze import scanner
from app.services.analyze.validator import validate


class FakeMessages:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.response_text)])


def _install_client(monkeypatch, response_text: str) -> FakeMessages:
    messages = FakeMessages(response_text)
    monkeypatch.setattr(
        scanner.anthropic,
        "Anthropic",
        lambda **_: SimpleNamespace(messages=messages),
    )
    return messages


def test_scan_file_parses_typed_json_and_sends_numbered_source(tmp_path: Path, monkeypatch):
    source = tmp_path / "app" / "orders.py"
    source.parent.mkdir()
    source.write_text("def submit(order):\n    return save(order)\n", encoding="utf-8")
    messages = _install_client(
        monkeypatch,
        """```json
[{"id":"controller-logic","dimension":"code_structure","severity":"medium","observation":"The entry point owns persistence orchestration.","evidence":{"file":"app/orders.py","lines":[1,2],"commit":null},"confidence":0.88}]
```""",
    )

    findings = scanner.scan_file(
        Settings(anthropic_api_key="test-key", scanner_model="test-model"),
        tmp_path,
        "app/orders.py",
    )

    assert [finding.id for finding in findings] == ["controller-logic"]
    assert findings[0].evidence.lines == (1, 2)
    assert messages.request["model"] == "test-model"
    assert "     1 | def submit(order):" in messages.request["messages"][0]["content"]


def test_scanner_candidates_still_pass_through_evidence_validator(tmp_path: Path, monkeypatch):
    source = tmp_path / "service.py"
    source.write_text("one line\n", encoding="utf-8")
    _install_client(
        monkeypatch,
        '[{"id":"invented-line","dimension":"domain_modelling","severity":"high","observation":"Unsupported citation.","evidence":{"file":"service.py","lines":[1,99]},"confidence":0.5}]',
    )

    candidates = scanner.scan_file(
        Settings(anthropic_api_key="test-key"), tmp_path, "service.py"
    )
    kept, dropped = validate(tmp_path, candidates)

    assert kept == []
    assert dropped == candidates


@pytest.mark.parametrize("response_text", ["not json", "{}", '[{"id":"incomplete"}]'])
def test_scan_file_rejects_malformed_model_output(tmp_path: Path, monkeypatch, response_text):
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    _install_client(monkeypatch, response_text)

    with pytest.raises(scanner.ScannerError):
        scanner.scan_file(Settings(anthropic_api_key="test-key"), tmp_path, "source.py")


def test_scan_file_requires_api_key_before_model_call(tmp_path: Path):
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        scanner.scan_file(Settings(anthropic_api_key=""), tmp_path, "source.py")


def test_scan_file_rejects_path_outside_repository(tmp_path: Path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("secret = True\n", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes"):
        scanner.scan_file(
            Settings(anthropic_api_key="test-key"), tmp_path, "../outside.py"
        )
