from __future__ import annotations

from pathlib import Path

from tether.docker import RunConfig, build_run_command
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
