"""Detection of persisted agent sessions, used to guard resume flags."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tether.mounts import opencode_data_dir


def opencode_has_session(project: Path) -> bool:
    """Return whether *project* has a persisted opencode session to resume.

    opencode aborts with an opaque "unexpected server error" when
    ``opencode --continue`` is run with no session, so callers check first. A
    missing database means there is nothing to resume; a database that cannot
    be read is treated optimistically as having a session.
    """
    database = opencode_data_dir(project) / "opencode.db"
    if not database.is_file():
        return False
    try:
        with sqlite3.connect(database) as connection:
            row = connection.execute("select count(*) from session").fetchone()
    except sqlite3.Error:
        return True
    return bool(row and row[0])
