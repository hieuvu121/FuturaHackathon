"""Dev server launcher:  python run.py

Reload must ignore cache/. Every repository cloned there is full of .py files,
so to the reloader a clone looks like a source change: the server restarts and
the background analysis dies mid-run.

`reload_dirs=["app"]` does NOT achieve that, though it looks as if it should.
uvicorn's WatchFiles reloader drops any reload dir that sits under the current
directory and then adds the current directory itself, so all of backend/ is
watched whatever is passed. What works is `reload_excludes` -- and only with
ABSOLUTE directory paths, because the filter tests them against the absolute
paths the watcher reports. tests/test_dev_server.py pins this down.

The port can be changed with PORT=8001 python run.py.
"""

import os
from pathlib import Path

import uvicorn

BACKEND_ROOT = Path(__file__).resolve().parent

# Directories whose .py files are not this application's source.
RELOAD_EXCLUDES = [str(BACKEND_ROOT / name) for name in ("cache", ".venv", "venv")]


def reload_excludes() -> list[str]:
    """Only directories that exist: uvicorn treats a missing path as a glob pattern."""
    return [path for path in RELOAD_EXCLUDES if Path(path).is_dir()]


if __name__ == "__main__":
    (BACKEND_ROOT / "cache").mkdir(exist_ok=True)
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        reload=True,
        reload_excludes=reload_excludes(),
    )
