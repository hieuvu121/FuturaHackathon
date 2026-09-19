"""Loads backend/mock/*.json.

Addition to the OVERALL.md tree: every router needed the same three lines, so
they live here once. Owned by Track D alongside the mock fixtures themselves.
"""

import json
from functools import lru_cache
from typing import Any

from .config import get_settings


@lru_cache
def load(name: str) -> Any:
    """load("scores") -> parsed backend/mock/scores.json"""
    path = get_settings().mock_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing mock fixture: {path}")
    return json.loads(path.read_text())
