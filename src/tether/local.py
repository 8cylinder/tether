"""Checks for host services that the container can use.

The functions here inspect the host only. ``tether local`` prints the result
and the commands needed to wire the service up; nothing is changed.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_BRIDGE_GATEWAY = "172.17.0.1"
DEFAULT_OLLAMA_CONTEXT_LENGTH = 4096
MIN_CONTEXT_LENGTH = 16384


@dataclass(frozen=True)
class OllamaModel:
    """A model advertised by the Ollama server."""

    name: str
    context_length: int | None
    capabilities: tuple[str, ...]

    @property
    def supports_tools(self) -> bool:
        return "tools" in self.capabilities


@dataclass(frozen=True)
class LoadedOllamaModel:
    """A model currently loaded by the Ollama server."""

    name: str
    context_length: int | None


def _get_json(url: str, *, timeout: float = 2.0) -> object | None:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except (OSError, ValueError):
        return None


def url_reachable(url: str) -> bool:
    """Return ``True`` when ``url`` answers with JSON."""
    return _get_json(url) is not None


def ollama_version() -> str | None:
    """Return the host Ollama version, or ``None`` when it is not running."""
    data = _get_json(f"{OLLAMA_URL}/api/version")
    if isinstance(data, dict):
        version = data.get("version")
        if isinstance(version, str):
            return version
    return None


def _context_length(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def ollama_models() -> list[OllamaModel]:
    """Return the models installed on the host Ollama server."""
    data = _get_json(f"{OLLAMA_URL}/api/tags")
    if not isinstance(data, dict):
        return []
    raw_models = data.get("models")
    if not isinstance(raw_models, list):
        return []
    models: list[OllamaModel] = []
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        if not isinstance(name, str):
            continue
        details = raw.get("details")
        context = _context_length(
            details.get("context_length") if isinstance(details, dict) else None
        )
        raw_capabilities = raw.get("capabilities")
        capabilities = (
            tuple(item for item in raw_capabilities if isinstance(item, str))
            if isinstance(raw_capabilities, list)
            else ()
        )
        models.append(
            OllamaModel(
                name=name,
                context_length=context,
                capabilities=capabilities,
            )
        )
    return models


def ollama_loaded() -> list[LoadedOllamaModel]:
    """Return the models the host Ollama server has loaded right now."""
    data = _get_json(f"{OLLAMA_URL}/api/ps")
    if not isinstance(data, dict):
        return []
    raw_models = data.get("models")
    if not isinstance(raw_models, list):
        return []
    loaded: list[LoadedOllamaModel] = []
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        if not isinstance(name, str):
            continue
        loaded.append(
            LoadedOllamaModel(
                name=name,
                context_length=_context_length(raw.get("context_length")),
            )
        )
    return loaded


def context_length(
    loaded: Sequence[LoadedOllamaModel], env: dict[str, str]
) -> int | None:
    """Return the context length the server is using, if it can be known.

    A loaded model reports the value it was started with, which is the most
    accurate source. Otherwise ``OLLAMA_CONTEXT_LENGTH`` is used. ``None``
    means the server is relying on its default.
    """
    for model in loaded:
        if model.context_length is not None:
            return model.context_length
    raw = env.get("OLLAMA_CONTEXT_LENGTH")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def container_reachable(env: dict[str, str], gateway: str) -> bool:
    """Return ``True`` when a container can reach the host Ollama server."""
    if url_reachable(f"http://{gateway}:11434/api/version"):
        return True
    bind = env.get("OLLAMA_HOST", "")
    return bind.startswith(("0.0.0.0:", "[::]", ":"))


def bridge_gateway() -> str:
    """Return the host address containers use for the default bridge."""
    if shutil.which("docker") is None:
        return DEFAULT_BRIDGE_GATEWAY
    try:
        result = subprocess.run(
            [
                "docker",
                "network",
                "inspect",
                "bridge",
                "--format",
                "{{(index .IPAM.Config 0).Gateway}}",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return DEFAULT_BRIDGE_GATEWAY
    if result.returncode != 0:
        return DEFAULT_BRIDGE_GATEWAY
    gateway = result.stdout.strip()
    return gateway or DEFAULT_BRIDGE_GATEWAY


def systemd_environment(unit: str = "ollama") -> dict[str, str]:
    """Return the effective systemd environment for ``unit``."""
    if shutil.which("systemctl") is None:
        return {}
    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                unit,
                "--property=Environment",
                "--value",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    env: dict[str, str] = {}
    for item in shlex.split(result.stdout):
        key, separator, value = item.partition("=")
        if separator:
            env[key] = value
    return env


def docker_host_access(args: Sequence[str]) -> bool:
    """Return ``True`` when docker args let the container reach the host."""
    for index, arg in enumerate(args):
        if arg == "--network=host":
            return True
        if (
            arg == "--network"
            and index + 1 < len(args)
            and args[index + 1] == "host"
        ):
            return True
        if arg.startswith("--add-host") and "host.docker.internal" in arg:
            return True
        if (
            arg == "--add-host"
            and index + 1 < len(args)
            and "host.docker.internal" in args[index + 1]
        ):
            return True
    return False
