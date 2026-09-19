"""Source slices for CodeViewer. Owner: Track A.

SECURITY: this endpoint takes client input and reads from disk. The resolved
absolute path MUST stay inside cache/<user>/<repo>/. See _safe_path below --
it is the whole reason this router is separate.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

from ..config import get_settings
from ..deps import CurrentUser

router = APIRouter(prefix="/repos", tags=["code"])


def _safe_path(user: str, repo_id: str, file: str) -> Path:
    """Resolves `file` inside the repo clone, or raises 400. Do not inline this."""
    root = (get_settings().cache_dir / user / repo_id).resolve()
    candidate = (root / file).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Path escapes the repository cache")
    return candidate


@router.get("/{repo_id}/code")
def code_slice(
    repo_id: str,
    user: CurrentUser,
    file: str = Query(...),
    start: int = Query(1, ge=1),
    end: int = Query(..., ge=1),
) -> dict[str, str | int | list[str]]:
    """Returns lines [start, end] of `file` from the cached clone."""
    if get_settings().mock_mode:
        return {
            "file": file,
            "start": start,
            "end": end,
            "lines": [f"# mock line {n} of {file}" for n in range(start, end + 1)],
        }
    raise NotImplementedError("Track A: read _safe_path(...) and slice it")
