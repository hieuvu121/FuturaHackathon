"""Deterministic parsing, metrics, test mapping, and smell detection."""

from pathlib import Path

import pytest

from app.services.ingest.metrics import enrich, smell_flags
from app.services.ingest.parser import parse_file


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_parser_extracts_decorated_nested_and_async_definitions(tmp_path: Path):
    _write(
        tmp_path,
        "app/service.py",
        """@decorator
class Service:
    @staticmethod
    def run(value):
        def normalise(item):
            return item.strip()
        return normalise(value)

async def fetch():
    return await client.get('/')
""",
    )

    functions = parse_file(tmp_path, "app/service.py")

    assert [function.name for function in functions] == [
        "Service",
        "Service.run",
        "Service.run.normalise",
        "fetch",
    ]
    assert functions[0].lines == (1, 7)
    assert functions[1].lines == (3, 7)
    assert functions[2].lines == (5, 6)
    assert functions[3].lines == (9, 10)
    assert all(function.loc == function.lines[1] - function.lines[0] + 1 for function in functions)


def test_parser_rejects_paths_outside_repository(tmp_path: Path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def hidden(): pass\n", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes"):
        parse_file(tmp_path, "../outside.py")


def test_metrics_compute_complexity_nesting_calls_and_test_mapping(tmp_path: Path):
    _write(
        tmp_path,
        "app/calculate.py",
        """def calculate(items, enabled):
    total = 0
    if enabled and items:
        for item in items:
            if item.valid:
                total += transform(item.value)
    return total
""",
    )
    _write(
        tmp_path,
        "tests/test_calculate.py",
        """from app.calculate import calculate

def test_calculate():
    assert calculate([], True) == 0
""",
    )
    functions = [
        *parse_file(tmp_path, "app/calculate.py"),
        *parse_file(tmp_path, "tests/test_calculate.py"),
    ]

    enriched = enrich(tmp_path, functions)
    calculate = next(function for function in enriched if function.name == "calculate")
    test_function = next(function for function in enriched if function.name == "test_calculate")

    assert calculate.complexity == 5  # baseline + if + and + for + nested if
    assert calculate.nesting_depth == 3
    assert calculate.calls == ["transform"]
    assert calculate.has_test is True
    assert test_function.calls == ["calculate"]
    assert test_function.has_test is True


def test_metrics_do_not_charge_nested_function_branches_to_parent(tmp_path: Path):
    _write(
        tmp_path,
        "nested.py",
        """def outer():
    def inner(value):
        if value:
            return True
        return False
    return inner(1)
""",
    )
    functions = parse_file(tmp_path, "nested.py")

    enrich(tmp_path, functions)

    outer = next(function for function in functions if function.name == "outer")
    inner = next(function for function in functions if function.name == "outer.inner")
    assert outer.complexity == 1
    assert outer.calls == ["inner"]
    assert inner.complexity == 2


def test_smell_flags_find_only_concrete_source_locations(tmp_path: Path):
    _write(
        tmp_path,
        "app/config.py",
        """API_KEY = 'live-secret-value'
safe_token = os.getenv('TOKEN')

def first():
    try:
        work()
    except Exception:
        pass

def second():
    try:
        work()
    except RuntimeError:
        return None

def third():
    try:
        work()
    except ValueError:
        raise
""",
    )

    flags = smell_flags(tmp_path, "app/config.py")

    assert [(flag["type"], flag["line"]) for flag in flags] == [
        ("hardcoded_secret", 1),
        ("empty_catch", 7),
        ("swallowed_exception", 7),
        ("swallowed_exception", 13),
    ]
    assert all(flag["file"] == "app/config.py" for flag in flags)
