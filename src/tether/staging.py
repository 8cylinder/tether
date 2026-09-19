"""Private staging for host files bind-mounted into the container.

A bind-mounted file must be usable by the container process regardless of the
uid it runs as: tether runs as the host uid on Linux but as the image's ``node``
uid (1000) on macOS, so the two platforms cannot both match the file owner. Each
staged file lives in a mode-0700 directory (private from other host users) and
is given an explicit file mode -- 0644 for read-only mounts and 0666 for the
read-write credentials file -- so any container uid can read or write it.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

READ_ONLY_MODE = 0o644
READ_WRITE_MODE = 0o666


@dataclass(frozen=True, slots=True)
class StagedFile:
    """A host file staged for a bind mount."""

    path: Path

    def cleanup(self) -> None:
        """Remove the staged file and its private directory."""
        shutil.rmtree(self.path.parent, ignore_errors=True)


def stage(content: str | bytes, *, mode: int, suffix: str = "") -> StagedFile:
    """Write *content* into a fresh private directory and return the staged file.

    Raises:
        OSError: when the file cannot be written, after cleaning up.
    """
    directory = Path(tempfile.mkdtemp(prefix="tether-stage-"))
    path = directory / f"content{suffix}"
    try:
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        path.chmod(mode)
    except OSError:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return StagedFile(path=path)
