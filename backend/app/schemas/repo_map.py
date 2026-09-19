"""repo_map.json — every function in the repo, metadata and pointers only.

Invariants (see OVERALL.md section 1):
  - Holds EVERY function, unfiltered. Filtering happens at query time, per purpose.
  - Stores pointers (file:lines:commit), never source code.
  - Produced deterministically by services/ingest. No LLM touches this file.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class FunctionNode(BaseModel):
    name: str
    file: str
    lines: tuple[int, int]

    # --- metrics.py ---
    complexity: int = Field(description="Cyclomatic complexity")
    nesting_depth: int = 0
    loc: int
    has_test: bool = False
    calls: list[str] = Field(default_factory=list, description="Names of callees")

    # --- gitlog.py ---
    times_modified: int = 0
    last_modified: datetime | None = None
    created_commit: str | None = None

    # --- blame.py (optional; 1.0 when blame is skipped) ---
    author_ratio: float = 1.0

    @property
    def qualified_name(self) -> str:
        return f"{self.file}::{self.name}"


class RepoMap(BaseModel):
    repo: str
    language: str
    analyzed_at: datetime
    total_files: int
    excluded_files: list[str] = Field(
        default_factory=list,
        description="Dropped by filter.py. Kept for explainability, not decoration.",
    )
    functions: list[FunctionNode] = Field(default_factory=list)
