from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tether.mounts import opencode_data_dir
from tether.sessions import opencode_has_session


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "proj"
    project.mkdir()
    return project


def _database(project: Path) -> Path:
    data = opencode_data_dir(project)
    data.mkdir(parents=True, exist_ok=True)
    return data / "opencode.db"


def _write(database: Path, *, sessions: int) -> None:
    connection = sqlite3.connect(database)
    try:
        connection.execute("create table session (id text)")
        for index in range(sessions):
            connection.execute("insert into session values (?)", (f"ses_{index}",))
        connection.commit()
    finally:
        connection.close()


def test_opencode_has_session_missing_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, monkeypatch)
    assert opencode_has_session(project) is False


def test_opencode_has_session_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _write(_database(project), sessions=0)
    assert opencode_has_session(project) is False


def test_opencode_has_session_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _write(_database(project), sessions=2)
    assert opencode_has_session(project) is True


def test_opencode_has_session_unreadable_is_optimistic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, monkeypatch)
    _database(project).write_bytes(b"not a sqlite database")
    assert opencode_has_session(project) is True
