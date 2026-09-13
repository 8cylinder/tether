"""Credential handling for the jail.

Secrets are forwarded with ``--env-file`` rather than ``--env KEY=VALUE`` so they
never appear in the host process list. The file is written with mode 0600 and
removed as soon as the container exits.

macOS Bedrock/SSO handling (host credential export, read-only ``~/.aws``) is
deferred until development moves to macOS.
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from tether.config import EnvConfig

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AuthError(ValueError):
    """Raised when credentials cannot be resolved or formatted."""


def collect_env(
    env_config: EnvConfig,
    host_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Merge static values with the host values named by ``passthrough``.

    Raises:
        AuthError: when a passthrough variable is not set on the host.
    """
    source = host_env if host_env is not None else os.environ
    missing = [name for name in env_config.passthrough if name not in source]
    if missing:
        raise AuthError("required environment variables are not set: " + ", ".join(sorted(missing)))

    resolved: dict[str, str] = dict(env_config.static)
    for name in env_config.passthrough:
        resolved[name] = source[name]
    return resolved


def _format_env(env: Mapping[str, str]) -> str:
    lines: list[str] = []
    for key, value in env.items():
        if not _ENV_NAME.match(key):
            raise AuthError(f"invalid environment variable name: {key!r}")
        if "\n" in value or "\r" in value or "\x00" in value:
            raise AuthError(f"environment value for {key} contains an unsupported character")
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def write_env_file(env: Mapping[str, str]) -> Path:
    """Write *env* to a fresh mode-0600 file and return its path."""
    handle, name = tempfile.mkstemp(prefix="tether-env-", suffix=".env")
    path = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(_format_env(env))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


@contextmanager
def env_file(env: Mapping[str, str]) -> Iterator[Path | None]:
    """Yield a temporary env-file path for *env*, cleaning it up afterwards.

    Yields ``None`` when *env* is empty.
    """
    if not env:
        yield None
        return
    path = write_env_file(env)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)
