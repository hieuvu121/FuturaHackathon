"""The dev reloader must not treat a cloned repository as a source change."""

import os
from pathlib import Path

from uvicorn.config import Config
from uvicorn.supervisors.watchfilesreload import FileFilter

import run


def test_reload_ignores_cloned_repositories_but_not_the_application(tmp_path, monkeypatch):
    for name in ("cache", ".venv", "app"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(run, "RELOAD_EXCLUDES", [str(tmp_path / "cache"), str(tmp_path / ".venv")])
    monkeypatch.chdir(tmp_path)

    watches = FileFilter(Config("app.main:app", reload=True, reload_excludes=run.reload_excludes()))

    assert watches(tmp_path / "app" / "routers" / "roadmap.py")
    assert not watches(tmp_path / "cache" / "dev" / "project" / "backend" / "app" / "main.py")
    assert not watches(tmp_path / ".venv" / "Lib" / "site-packages" / "thing.py")


def test_excludes_are_absolute_and_skip_directories_that_do_not_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "RELOAD_EXCLUDES", [str(tmp_path / "cache"), str(tmp_path / "venv")])
    (tmp_path / "cache").mkdir()

    found = run.reload_excludes()

    # A relative path would never match what the watcher reports, and a missing
    # one would be read as a glob pattern instead of a directory.
    assert found == [str(tmp_path / "cache")]
    assert all(os.path.isabs(path) for path in found)


def test_the_real_cache_directory_is_excluded():
    assert str(Path(run.__file__).resolve().parent / "cache") in run.RELOAD_EXCLUDES
