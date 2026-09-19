"""Debug-question bug injection. Owner: Track B.

Takes a function WITH passing tests, asks the model to introduce a realistic bug,
then RUNS THE TEST SUITE to confirm the bug actually fails a test. Regenerates if
it does not. Returns the broken code, the fix, and the grading tests.

The verification run is the point. An injected bug that no test catches is useless.
"""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

import anthropic
from openai import OpenAI
from pydantic import BaseModel

from ...config import Settings
from ...schemas.repo_map import FunctionNode


class InjectionError(RuntimeError):
    pass


class InjectionCandidate(BaseModel):
    broken_code: str
    fix: str


def _source_path(root: Path, rel_path: str) -> Path:
    root = root.resolve()
    path = (root / rel_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Target path is outside the repository: {rel_path}")
    return path


def _function_source(root: Path, target: FunctionNode) -> str:
    lines = _source_path(root, target.file).read_text(encoding="utf-8", errors="replace").splitlines()
    start, end = target.lines
    if start < 1 or end < start or end > len(lines):
        raise ValueError("Target line range is invalid")
    return "\n".join(lines[start - 1 : end])


def _replace_function(root: Path, target: FunctionNode, replacement: str) -> None:
    path = _source_path(root, target.file)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start, end = target.lines
    updated = [*lines[: start - 1], *replacement.splitlines(), *lines[end:]]
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _test_command() -> list[str]:
    return [sys.executable, "-m", "pytest", "-q"]


def _run_tests(root: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    try:
        return subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise InjectionError("Repository test suite exceeded 120 seconds") from exc


def _candidate(settings: Settings, target: FunctionNode, source: str, attempt: int) -> InjectionCandidate:
    prompt = (
        "Introduce one subtle, realistic logic bug into this Python function. "
        "Keep its signature and return only the complete broken function plus the exact original fix. "
        f"Attempt {attempt}.\n\n{source}"
    )
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        response = OpenAI(api_key=settings.openai_api_key).responses.parse(
            model=(
                settings.scanner_model
                if settings.generator_model.casefold().startswith("claude")
                else settings.generator_model
            ),
            input=[{"role": "user", "content": prompt}],
            text_format=InjectionCandidate,
        )
        if response.output_parsed is None:
            raise InjectionError("Model returned no injection candidate")
        return response.output_parsed
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    response = anthropic.Anthropic(api_key=settings.anthropic_api_key).messages.create(
        model=settings.generator_model,
        max_tokens=2_000,
        temperature=0,
        messages=[{"role": "user", "content": prompt + "\nReturn JSON with broken_code and fix."}],
    )
    text = "\n".join(block.text for block in response.content if block.type == "text")
    return InjectionCandidate.model_validate(json.loads(text))


def inject_bug(settings: Settings, root: Path, target: FunctionNode, max_attempts: int = 3) -> dict:
    """-> {"broken_code": str, "fix": str, "test_command": str, "failing_test": str}"""
    if not target.has_test:
        raise InjectionError("Debug injection requires a target with existing tests")
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    root = root.resolve()
    original = _function_source(root, target)
    command = _test_command()

    with tempfile.TemporaryDirectory(prefix="futura-inject-") as temp_dir:
        workspace = Path(temp_dir) / "repo"
        shutil.copytree(root, workspace, ignore=shutil.ignore_patterns(".git", ".venv", "venv"))
        baseline = _run_tests(workspace, command)
        if baseline.returncode != 0:
            raise InjectionError("Repository tests must pass before bug injection")

        for attempt in range(1, max_attempts + 1):
            candidate = _candidate(settings, target, original, attempt)
            if candidate.fix.strip() != original.strip() or candidate.broken_code.strip() == original.strip():
                continue
            _replace_function(workspace, target, original)
            _replace_function(workspace, target, candidate.broken_code)
            result = _run_tests(workspace, command)
            if result.returncode != 0:
                output = (result.stdout + "\n" + result.stderr).strip()
                return {
                    "broken_code": candidate.broken_code,
                    "fix": candidate.fix,
                    "test_command": shlex.join(command),
                    "failing_test": output[-4_000:],
                }
    raise InjectionError(f"No injected bug failed the test suite after {max_attempts} attempts")
