"""Mount policy: which host paths are exposed inside the jail."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tether.config import Mount

WORKSPACE = "/workspace"
GIT_DIR = ".git"
CONTAINER_CLAUDE_DIR = "/tmp/tether-home/.claude"
CONTAINER_CLAUDE_JSON = "/tmp/tether-home/.claude.json"
CONTAINER_AWS_CREDENTIALS = "/tmp/tether-home/.aws/credentials"


class MountError(ValueError):
    """Raised when a mount cannot be constructed."""


@dataclass(frozen=True, slots=True)
class ContainerMount:
    """A host path bound into the container."""

    source: Path
    target: str
    mode: str

    def as_docker_arg(self) -> str:
        """Return the ``--volume`` value for this mount."""
        return f"{self.source}:{self.target}:{self.mode}"


def resolve_project(path: Path) -> Path:
    """Resolve *path* to an existing project directory.

    Raises:
        MountError: when the path is missing or not a directory.
    """
    project = path.expanduser().resolve()
    if not project.exists():
        raise MountError(f"project directory does not exist: {project}")
    if not project.is_dir():
        raise MountError(f"project path is not a directory: {project}")
    return project


def has_git(project: Path) -> bool:
    """Return whether *project* contains a ``.git`` directory."""
    return (project / GIT_DIR).is_dir()


def build_mounts(project: Path, *, extra: list[Mount] | None = None) -> list[ContainerMount]:
    """Build the mount policy for *project*.

    The project is mounted read-write at ``/workspace``. Its ``.git`` directory
    is mounted read-only on top, so the agent cannot rewrite history or delete
    the repository.

    Raises:
        MountError: when an extra mount source does not exist.
    """
    mounts = [ContainerMount(source=project, target=WORKSPACE, mode="rw")]

    if has_git(project):
        mounts.append(
            ContainerMount(
                source=project / GIT_DIR,
                target=f"{WORKSPACE}/{GIT_DIR}",
                mode="ro",
            )
        )

    for mount in extra or []:
        source = Path(mount.source).expanduser().resolve()
        if not source.exists():
            raise MountError(f"mount source does not exist: {source}")
        mounts.append(ContainerMount(source=source, target=mount.target, mode=mount.mode))

    return mounts


_SETTINGS_KEYS_TO_STRIP = {"env", "awsAuthRefresh", "permissions", "sandbox"}

_TETHER_STATUS_LINE = {"type": "command", "command": "echo '⚛️ tether ⚛️'"}

CONTAINER_CLAUDE_SETTINGS = f"{CONTAINER_CLAUDE_DIR}/settings.json"


def _filter_claude_settings(source: Path) -> Path:
    """Read *source*, strip conflicting keys, inject tether statusLine, write a temp copy."""
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    for key in _SETTINGS_KEYS_TO_STRIP:
        data.pop(key, None)
    data["statusLine"] = _TETHER_STATUS_LINE
    data["sandbox"] = {"enabled": False}
    data["permissions"] = {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    handle, name = tempfile.mkstemp(prefix="tether-claude-settings-", suffix=".json")
    with os.fdopen(handle, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return Path(name)


def claude_config_mounts() -> tuple[list[ContainerMount], list[Path]]:
    """Return read-write mounts for Claude Code config and any temp files to clean up.

    Mounts ``~/.claude/`` and ``~/.claude.json``.  If ``~/.claude/settings.json``
    contains keys that conflict with container auth (``env``, ``awsAuthRefresh``),
    a filtered copy is mounted on top of the original.
    """
    mounts: list[ContainerMount] = []
    temp_files: list[Path] = []
    claude_dir = Path.home() / ".claude"
    if claude_dir.is_dir():
        mounts.append(ContainerMount(source=claude_dir, target=CONTAINER_CLAUDE_DIR, mode="ro"))
        filtered = _filter_claude_settings(claude_dir / "settings.json")
        mounts.append(
            ContainerMount(source=filtered, target=CONTAINER_CLAUDE_SETTINGS, mode="ro")
        )
        temp_files.append(filtered)
    claude_json = Path.home() / ".claude.json"
    if claude_json.is_file():
        mounts.append(ContainerMount(source=claude_json, target=CONTAINER_CLAUDE_JSON, mode="rw"))
    return mounts, temp_files
