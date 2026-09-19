"""Source slices for CodeViewer. Owner: Track A.

SECURITY: this endpoint takes client input and reads from disk. The resolved
absolute path MUST stay inside cache/<user>/<repo>/. See _safe_path below --
it is the whole reason this router is separate.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

from ..config import get_settings
from sqlalchemy import select

from ..deps import CurrentUser, DbDep
from ..models.db import Repo, User

router = APIRouter(prefix="/repos", tags=["code"])


def _safe_path(user: str, repo_id: str, file: str) -> Path:
    """Resolves `file` inside the repo clone, or raises 400. Do not inline this."""
    root = (get_settings().cache_dir / user / repo_id).resolve()
    candidate = (root / file).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Path escapes the repository cache")
    return candidate


def _safe_path_from_root(root: Path, file: str) -> Path:
    root = root.resolve()
    candidate = (root / file).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Path escapes the repository cache")
    return candidate


def _read_slice(path: Path, start: int, end: int) -> list[str]:
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "End line must not precede start line")
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source file not found")

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source file could not be read") from exc
    if end > len(lines):
        raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "Line range exceeds file")
    return lines[start - 1 : end]


@router.get("/{repo_id}/code")
def code_slice(
    repo_id: str,
    user: CurrentUser,
    db: DbDep,
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

    try:
        numeric_repo_id = int(repo_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found") from exc
    repo = db.scalar(
        select(Repo)
        .join(User, Repo.user_id == User.id)
        .where(Repo.id == numeric_repo_id, User.github_login == user)
    )
    if repo is None or not repo.clone_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository clone not found")

    path = _safe_path_from_root(Path(repo.clone_path), file)
    return {"file": file, "start": start, "end": end, "lines": _read_slice(path, start, end)}
