"""Debug-question bug injection. Owner: Track B.

Takes a function WITH passing tests, asks the model to introduce a realistic bug,
then RUNS THE TEST SUITE to confirm the bug actually fails a test. Regenerates if
it does not. Returns the broken code, the fix, and the grading tests.

The verification run is the point. An injected bug that no test catches is useless.
"""

from pathlib import Path

from ...config import Settings
from ...schemas.repo_map import FunctionNode


def inject_bug(settings: Settings, root: Path, target: FunctionNode, max_attempts: int = 3) -> dict:
    """-> {"broken_code": str, "fix": str, "test_command": str, "failing_test": str}"""
    raise NotImplementedError
