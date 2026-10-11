from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tether import docker


class Recorder:
    def __init__(self, returncode: int = 0) -> None:
        self.commands: list[list[str]] = []
        self.returncode = returncode

    def __call__(self, command: list[str], **kwargs: object) -> SimpleNamespace:
        self.commands.append(command)
        return SimpleNamespace(returncode=self.returncode, stdout="", stderr="")


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(docker.subprocess, "run", rec)
    return rec


def test_image_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker.subprocess, "run", Recorder(returncode=0))
    assert docker.image_exists("tether:latest") is True
    monkeypatch.setattr(docker.subprocess, "run", Recorder(returncode=1))
    assert docker.image_exists("tether:latest") is False


def test_build_image(recorder: Recorder) -> None:
    docker.build_image("tether:latest", uid=1001, gid=1002)

    command = recorder.commands[0]
    assert command[:2] == ["docker", "build"]
    assert "--tag" in command and "tether:latest" in command
    assert "UID=1001" in command
    assert "GID=1002" in command


def test_build_image_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker.subprocess, "run", Recorder(returncode=2))
    with pytest.raises(docker.DockerError):
        docker.build_image("tether:latest", uid=1000, gid=1000)


def test_run_container(recorder: Recorder, tmp_path: Path) -> None:
    docker.run_container(
        "tether:latest",
        tmp_path,
        [(str(tmp_path), "/home/tether/.config/opencode")],
        ["opencode"],
    )

    command = recorder.commands[0]
    assert command[:2] == ["docker", "run"]
    assert "--rm" in command
    assert f"{tmp_path}:/workdir" in command
    assert f"{tmp_path}:/home/tether/.config/opencode" in command
    assert command[-2:] == ["tether:latest", "opencode"]


def test_remove_image(recorder: Recorder) -> None:
    assert docker.remove_image("tether:latest") is True
    assert recorder.commands[-1][:3] == ["docker", "image", "rm"]


def test_remove_missing_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker.subprocess, "run", Recorder(returncode=1))
    assert docker.remove_image("tether:latest") is False


def test_docker_version_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker.shutil, "which", lambda _: None)
    assert docker.docker_version() is None


def test_subprocess_module_default() -> None:
    assert subprocess is docker.subprocess
