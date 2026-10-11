"""Loading and resolving ``~/.config/tether/config.toml``."""

from __future__ import annotations

import tomllib
import warnings
from dataclasses import dataclass
from pathlib import Path

from tether.harnesses import DEFAULT_AGENT, HARNESSES
from tether.util import container_path_for, expand_host_path, looks_like_file

CONFIG_PATH = Path.home() / ".config" / "tether" / "config.toml"

CONFIG_TEMPLATE = """\
# tether configuration
#
# `default` selects the harness used by `tether run` when --agent is omitted.
# Each section lists host paths bind-mounted into the container so that
# settings, prompts and history survive between sessions. `~` and environment
# variables are expanded. Missing directories are created on first run; missing
# files are skipped.

default = "opencode"

[opencode]
mount = [
    "~/.config/opencode",
    "~/.local/share/opencode",
    "~/.local/state/opencode",
    "~/.cache/opencode",
]

[claude]
mount = [
    "~/.claude",
    "~/.claude.json",
    "~/.config/claude",
]

[antigravity]
mount = [
    "~/.gemini/antigravity-cli",
    "~/.antigravity",
]
"""


class ConfigError(RuntimeError):
    """Raised when the configuration file is malformed."""


@dataclass
class Config:
    path: Path
    default_agent: str
    mounts: dict[str, list[str]]

    def raw_mounts_for(self, agent: str) -> list[str]:
        return list(self.mounts.get(agent, HARNESSES[agent].default_mounts))


def load_config(path: Path | None = None, *, create: bool = True) -> Config:
    """Load the config file, creating it with defaults if it does not exist."""
    config_path = Path(path) if path is not None else CONFIG_PATH

    if config_path.exists():
        try:
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:  # pragma: no cover - message passthrough
            raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc
    else:
        if create:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        data = tomllib.loads(CONFIG_TEMPLATE)

    default_agent = data.get("default") or data.get("deafault") or DEFAULT_AGENT
    if default_agent not in HARNESSES:
        warnings.warn(
            f"Unknown default harness {default_agent!r}; falling back to {DEFAULT_AGENT!r}.",
            stacklevel=2,
        )
        default_agent = DEFAULT_AGENT

    mounts: dict[str, list[str]] = {}
    for name, harness in HARNESSES.items():
        section = data.get(name)
        if section is None:
            mounts[name] = list(harness.default_mounts)
            continue
        if not isinstance(section, dict):
            raise ConfigError(f"Section [{name}] must be a table.")
        raw = section.get("mount")
        if raw is None:
            mounts[name] = list(harness.default_mounts)
        elif not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise ConfigError(f"[{name}].mount must be a list of strings.")
        else:
            mounts[name] = list(raw)

    return Config(path=config_path, default_agent=default_agent, mounts=mounts)


def resolve_mounts(
    config: Config,
    agent: str,
    *,
    create_missing: bool = True,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Resolve host mount paths for ``agent``.

    Returns ``(mounts, skipped)`` where ``mounts`` is a list of
    ``(host_path, container_path)`` pairs and ``skipped`` records paths that
    could not be mounted with a reason.

    The bind source is resolved (following symlinks) while the container path is
    derived from the logical path, so a symlinked mount directory still lands
    where the harness looks for it.
    """
    mounts: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    seen_hosts: set[str] = set()
    seen_containers: set[str] = set()

    def add(host: Path, container: str) -> None:
        host_str = str(host)
        if host_str in seen_hosts or container in seen_containers:
            return
        seen_hosts.add(host_str)
        seen_containers.add(container)
        mounts.append((host_str, container))

    for raw in config.raw_mounts_for(agent):
        logical = expand_host_path(raw)

        if logical.is_symlink() and not logical.exists():
            skipped.append((raw, "broken symlink"))
            continue

        if not logical.exists():
            if looks_like_file(logical):
                skipped.append((raw, "file does not exist"))
                continue
            if create_missing:
                logical.mkdir(parents=True, exist_ok=True)
            else:
                skipped.append((raw, "does not exist"))
                continue

        container = container_path_for(logical)
        source = logical.resolve()
        add(source, container)

    return mounts, skipped
