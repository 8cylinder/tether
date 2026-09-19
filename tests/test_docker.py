from __future__ import annotations

from pathlib import Path

import pytest

from tether.docker import (
    AGENT_PACKAGES,
    DockerError,
    RunConfig,
    _fetch_latest_version,
    build_run_command,
    resolve_agent_build_args,
)
from tether.mounts import ContainerMount


def _mount(tmp_path: Path) -> ContainerMount:
    return ContainerMount(source=tmp_path, target="/workspace", mode="rw")


def test_build_run_command_hardening(tmp_path: Path) -> None:
    config = RunConfig(
        image="tether:latest",
        command=("claude", "--permission-mode", "plan"),
        mounts=(_mount(tmp_path),),
        user="1000:1000",
        memory="4g",
        cpus="2",
        pids_limit=1024,
        tty=False,
    )
    command = build_run_command(config, docker="docker")

    assert command[0] == "docker"
    assert "--rm" in command
    assert "--init" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--security-opt") + 1] == "no-new-privileges"
    assert command[command.index("--user") + 1] == "1000:1000"
    assert command[command.index("--pids-limit") + 1] == "1024"
    assert command[command.index("--memory") + 1] == "4g"
    assert command[command.index("--cpus") + 1] == "2"
    assert f"{tmp_path}:/workspace:rw" in command
    assert "--tty" not in command
    assert command[-3:] == ["claude", "--permission-mode", "plan"]


def test_build_run_command_minimal(tmp_path: Path) -> None:
    config = RunConfig(image="img", command=("bash",), mounts=(_mount(tmp_path),))
    command = build_run_command(config, docker="docker")

    assert "--user" not in command
    assert "--memory" not in command
    assert command[command.index("--workdir") + 1] == "/workspace"
    assert command[-2:] == ["img", "bash"]


def test_build_run_command_tty() -> None:
    config = RunConfig(image="img", command=("bash",), mounts=(), tty=True)
    command = build_run_command(config, docker="docker")
    assert "--tty" in command
    assert "--interactive" in command


def test_build_run_command_env_file(tmp_path: Path) -> None:
    config = RunConfig(
        image="img",
        command=("bash",),
        mounts=(_mount(tmp_path),),
        env_file="/tmp/tether.env",
    )
    command = build_run_command(config, docker="docker")
    assert command[command.index("--env-file") + 1] == "/tmp/tether.env"


def test_build_run_command_without_env_file(tmp_path: Path) -> None:
    config = RunConfig(image="img", command=("bash",), mounts=(_mount(tmp_path),))
    command = build_run_command(config, docker="docker")
    assert "--env-file" not in command


def test_build_run_command_with_name(tmp_path: Path) -> None:
    config = RunConfig(
        image="img",
        command=("bash",),
        mounts=(_mount(tmp_path),),
        name="tether-myproject-abc123",
    )
    command = build_run_command(config, docker="docker")
    assert command[command.index("--name") + 1] == "tether-myproject-abc123"


def test_build_run_command_without_name(tmp_path: Path) -> None:
    config = RunConfig(image="img", command=("bash",), mounts=(_mount(tmp_path),))
    command = build_run_command(config, docker="docker")
    assert "--name" not in command


def test_resolve_agent_build_args_uses_fetcher() -> None:
    versions = {package: f"1.0.{index}" for index, package in enumerate(AGENT_PACKAGES.values())}
    calls: list[str] = []

    def fake_fetch(package: str) -> str:
        calls.append(package)
        return versions[package]

    build_args = resolve_agent_build_args(fetcher=fake_fetch)

    assert build_args == {key: versions[package] for key, package in AGENT_PACKAGES.items()}
    assert calls == list(AGENT_PACKAGES.values())


def test_resolve_agent_build_args_propagates_error() -> None:
    def fake_fetch(_package: str) -> str:
        raise DockerError("registry unavailable")

    with pytest.raises(DockerError):
        resolve_agent_build_args(fetcher=fake_fetch)


def test_fetch_latest_version_reads_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def read(self) -> bytes:
            return b'{"version": "1.2.3"}'

    def fake_urlopen(url: str, timeout: float = 0) -> _Response:
        captured["url"] = url
        captured["timeout"] = str(timeout)
        return _Response()

    monkeypatch.setattr("tether.docker.urllib.request.urlopen", fake_urlopen)

    assert _fetch_latest_version("@anthropic-ai/claude-code") == "1.2.3"
    assert captured["url"] == "https://registry.npmjs.org/@anthropic-ai%2fclaude-code/latest"


def test_fetch_latest_version_rejects_missing_version(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def read(self) -> bytes:
            return b"{}"

    monkeypatch.setattr(
        "tether.docker.urllib.request.urlopen",
        lambda url, timeout=0: _Response(),
    )

    with pytest.raises(DockerError):
        _fetch_latest_version("opencode-ai")
