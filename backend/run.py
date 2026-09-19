"""Dev server launcher:  python run.py

Reload watches app/ ONLY. Plain `uvicorn --reload` watches all of backend/, so
every repository cloned into cache/ looks like a source change, the server
restarts, and the background analysis dies mid-run.
"""

from pathlib import Path

import uvicorn

BACKEND_ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(BACKEND_ROOT / "app")],
    )
