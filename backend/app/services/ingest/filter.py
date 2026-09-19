"""Decides which files are the user's own work. Owner: Track A.

Excludes: dependency dirs (node_modules, vendor, venv), generated code and
scaffolding, build output, lock and minified files, and forks with no original
commits. Returns kept paths PLUS the exclusion list -- the exclusions are shown
in the UI for explainability, so do not throw them away.
"""

from pathlib import Path

EXCLUDED_DIRS = {
    "node_modules", "vendor", "venv", ".venv", "env", "site-packages",
    "dist", "build", "out", "target", ".next", "__pycache__", ".git",
    "migrations", "generated",
}
EXCLUDED_SUFFIXES = {".min.js", ".min.css", ".lock", ".map", ".pb.go", "_pb2.py"}
EXCLUDED_NAMES = {"package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock"}


def filter_files(root: Path, language: str, is_fork: bool) -> tuple[list[str], list[str]]:
    """Returns (kept_paths, excluded_paths), both relative to root."""
    raise NotImplementedError
