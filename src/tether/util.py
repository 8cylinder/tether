"""Shared constants and path helpers."""

from __future__ import annotations

import os
from pathlib import Path

CONTAINER_HOME = "/home/tether"
CONTAINER_WORKDIR = "/workdir"
CONTAINER_USER = "tether"

IMAGE_NAME = "tether:latest"


def expand_host_path(raw: str, base: Path | None = None) -> Path:
    """Expand ``~`` and environment variables into an absolute path.

    Relative paths are resolved against ``base`` (the config file's directory
    for paths read from config) instead of the current working directory.
    Symlinks are deliberately *not* resolved here. The logical path is used to
    decide where the mount lands in the container, while the bind source is
    resolved separately (see :func:`tether.config.resolve_mounts`). Resolving
    both would move a symlinked mount to the wrong container path.
    """
    expanded = os.path.expanduser(os.path.expandvars(raw))
    path = Path(expanded)
    if not path.is_absolute():
        path = (base if base is not None else Path.cwd()) / path
    return Path(os.path.abspath(path))


def looks_like_file(path: Path) -> bool:
    """Heuristic: a path with a file extension is treated as a file.

    Leading-dot names such as ``.claude`` are directories, not files.
    """
    return bool(path.suffix)


def container_path_for(host_path: Path, host_home: Path | None = None) -> str:
    """Map a host path into the container, keeping ``$HOME`` paths parallel."""
    host_home = host_home or Path.home()
    try:
        relative = host_path.relative_to(host_home)
    except ValueError:
        return str(host_path)
    return str(Path(CONTAINER_HOME) / relative)


def host_uid_gid() -> tuple[int, int]:
    return os.getuid(), os.getgid()
