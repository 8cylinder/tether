"""Mount policy: which host paths are exposed inside the jail."""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass
from pathlib import Path

from tether.config import Mount
from tether.staging import READ_ONLY_MODE, StagedFile, stage

WORKSPACE = "/workspace"
GIT_DIR = ".git"
CONTAINER_CLAUDE_DIR = "/tmp/tether-home/.claude"
CONTAINER_CLAUDE_JSON = "/tmp/tether-home/.claude.json"
CONTAINER_AWS_CREDENTIALS = "/tmp/tether-home/.aws/credentials"
CONTAINER_OPENCODE_CONFIG_DIR = "/tmp/tether-home/opencode-config"
CONTAINER_OPENCODE_CONFIG_BASE = "/tmp/tether-home/opencode-config-file"


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


_DENIED_MOUNT_SOURCES = frozenset(
    Path(p).expanduser().resolve()
    for p in ("/", "/etc", "/var", "~/.ssh", "~/.aws", "~/.gnupg", "~/.config")
)

_DENIED_MOUNT_TARGETS = frozenset(("/var/run/docker.sock",))
_WORKSPACE_PREFIX = f"{WORKSPACE}/"


def _check_mount_safety(source: Path, target: str) -> None:
    """Raise if *source* or *target* would expose or override a protected path."""
    if source in _DENIED_MOUNT_SOURCES:
        raise MountError(f"refusing to mount dangerous path: {source}")
    if str(source) in _DENIED_MOUNT_TARGETS:
        raise MountError(f"refusing to mount dangerous path: {source}")
    normalized = posixpath.normpath(target)
    if normalized in _DENIED_MOUNT_TARGETS:
        raise MountError(f"refusing to mount dangerous target: {target}")
    if normalized == WORKSPACE or normalized.startswith(_WORKSPACE_PREFIX):
        raise MountError(f"refusing to mount over the managed workspace: {target}")


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
        _check_mount_safety(source, mount.target)
        mounts.append(ContainerMount(source=source, target=mount.target, mode=mount.mode))

    return mounts


_SETTINGS_KEYS_TO_STRIP = {"env", "awsAuthRefresh", "permissions", "sandbox"}

_TETHER_STATUS_LINE = {"type": "command", "command": "echo '⚛️ tether ⚛️'"}

CONTAINER_CLAUDE_SETTINGS = f"{CONTAINER_CLAUDE_DIR}/settings.json"


def _filter_claude_settings(source: Path) -> StagedFile:
    """Read *source*, strip conflicting keys, inject tether statusLine, stage a copy."""
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    for key in _SETTINGS_KEYS_TO_STRIP:
        data.pop(key, None)
    data["statusLine"] = _TETHER_STATUS_LINE
    data["sandbox"] = {"enabled": False}
    data["permissions"] = {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    return stage(json.dumps(data, indent=2) + "\n", mode=READ_ONLY_MODE, suffix=".json")


def claude_config_mounts() -> tuple[list[ContainerMount], list[StagedFile]]:
    """Return mounts for Claude Code config and any staged files to clean up.

    Mounts ``~/.claude/`` and ``~/.claude.json``.  If ``~/.claude/settings.json``
    contains keys that conflict with container auth (``env``, ``awsAuthRefresh``),
    a filtered copy is mounted on top of the original.
    """
    mounts: list[ContainerMount] = []
    staged_files: list[StagedFile] = []
    claude_dir = Path.home() / ".claude"
    if claude_dir.is_dir():
        mounts.append(ContainerMount(source=claude_dir, target=CONTAINER_CLAUDE_DIR, mode="ro"))
        filtered = _filter_claude_settings(claude_dir / "settings.json")
        mounts.append(
            ContainerMount(source=filtered.path, target=CONTAINER_CLAUDE_SETTINGS, mode="ro")
        )
        staged_files.append(filtered)
    claude_json = Path.home() / ".claude.json"
    if claude_json.is_file():
        mounts.append(ContainerMount(source=claude_json, target=CONTAINER_CLAUDE_JSON, mode="rw"))
    return mounts, staged_files


def _copy_opencode_config(source: Path) -> StagedFile:
    """Stage *source*, following symlinks, for read-only mounting."""
    return stage(source.read_bytes(), mode=READ_ONLY_MODE, suffix=source.suffix)


def opencode_config_mounts() -> tuple[list[ContainerMount], list[StagedFile], dict[str, str]]:
    """Return read-only mounts for opencode config, staged files, and env vars.

    Mounts ``~/.config/opencode`` at a non-default path (exposed through
    ``OPENCODE_CONFIG_DIR``) so agents, commands, and plugins carry over. A
    top-level ``opencode.json``/``opencode.jsonc`` is copied -- following
    symlinks to host paths that would dangle inside the container -- and mounted
    separately, exposed through ``OPENCODE_CONFIG``. Mounting at non-default
    paths avoids Docker resolving a symlinked config to its host target.
    """
    mounts: list[ContainerMount] = []
    staged_files: list[StagedFile] = []
    env: dict[str, str] = {}
    config_dir = Path.home() / ".config" / "opencode"
    if not config_dir.is_dir():
        return mounts, staged_files, env
    mounts.append(
        ContainerMount(source=config_dir, target=CONTAINER_OPENCODE_CONFIG_DIR, mode="ro")
    )
    env["OPENCODE_CONFIG_DIR"] = CONTAINER_OPENCODE_CONFIG_DIR
    for name in ("opencode.json", "opencode.jsonc"):
        candidate = config_dir / name
        if candidate.is_file():
            copied = _copy_opencode_config(candidate)
            staged_files.append(copied)
            target = f"{CONTAINER_OPENCODE_CONFIG_BASE}{candidate.suffix}"
            mounts.append(ContainerMount(source=copied.path, target=target, mode="ro"))
            env["OPENCODE_CONFIG"] = target
            break
    return mounts, staged_files, env
