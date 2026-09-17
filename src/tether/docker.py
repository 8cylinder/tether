"""Docker image build and container execution helpers."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from tether.mounts import ContainerMount
from tether.platform import find_docker


class DockerError(RuntimeError):
    """Raised when Docker is unavailable or a command fails."""


def docker_assets_dir() -> Path:
    """Return the directory holding the Dockerfile and entrypoint script."""
    return Path(__file__).resolve().parent / "assets" / "docker"


def dockerfile_path() -> Path:
    """Return the path to the bundled Dockerfile."""
    return docker_assets_dir() / "Dockerfile"


def require_docker() -> str:
    """Return the path to the docker CLI.

    Raises:
        DockerError: when docker is not installed.
    """
    docker = find_docker()
    if docker is None:
        raise DockerError("docker CLI not found on PATH")
    return docker


def container_running(name: str) -> bool:
    """Return whether a container with *name* is currently running."""
    docker = require_docker()
    result = subprocess.run(
        [docker, "ps", "--quiet", "--filter", f"name=^/{name}$"],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())


def image_exists(image: str) -> bool:
    """Return whether *image* is present in the local Docker image store."""
    docker = require_docker()
    result = subprocess.run(
        [docker, "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Outcome of an image build request."""

    image: str
    built: bool


def build_image(
    image: str,
    *,
    force: bool = False,
    build_args: dict[str, str] | None = None,
) -> BuildResult:
    """Build the jail image unless it already exists.

    Raises:
        DockerError: when Docker is unavailable or the build fails.
    """
    if not force and image_exists(image):
        return BuildResult(image=image, built=False)

    docker = require_docker()
    command = [docker, "build", "--tag", image, "--file", str(dockerfile_path())]
    for key, value in (build_args or {}).items():
        command += ["--build-arg", f"{key}={value}"]
    command.append(str(docker_assets_dir()))

    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise DockerError(f"docker build failed with exit code {exc.returncode}") from exc
    except OSError as exc:
        raise DockerError(f"failed to run docker: {exc}") from exc

    return BuildResult(image=image, built=True)


@dataclass(frozen=True, slots=True)
class RunConfig:
    """Parameters describing a single jail launch."""

    image: str
    command: tuple[str, ...]
    mounts: tuple[ContainerMount, ...]
    workdir: str = "/workspace"
    env_file: str | None = None
    user: str | None = None
    name: str | None = None
    memory: str | None = None
    cpus: str | None = None
    pids_limit: int | None = None
    interactive: bool = True
    tty: bool = False


def build_run_command(config: RunConfig, *, docker: str = "docker") -> list[str]:
    """Build the ``docker run`` argv for *config*."""
    command = [docker, "run", "--rm"]
    if config.name:
        command += ["--name", config.name]
    if config.interactive:
        command.append("--interactive")
    if config.tty:
        command.append("--tty")
    command += ["--init", "--workdir", config.workdir]
    if config.user:
        command += ["--user", config.user]
    for mount in config.mounts:
        command += ["--volume", mount.as_docker_arg()]
    if config.env_file:
        command += ["--env-file", config.env_file]
    command += [
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
    ]
    if config.pids_limit is not None:
        command += ["--pids-limit", str(config.pids_limit)]
    if config.memory:
        command += ["--memory", config.memory]
    if config.cpus:
        command += ["--cpus", config.cpus]
    command.append(config.image)
    command.extend(config.command)
    return command


def run_container(config: RunConfig) -> int:
    """Run the jail container and return its exit code.

    Raises:
        DockerError: when Docker is unavailable or cannot be started.
    """
    docker = require_docker()
    command = build_run_command(config, docker=docker)
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        raise DockerError(f"failed to run docker: {exc}") from exc
    return result.returncode


def exec_in_container(
    name: str,
    command: tuple[str, ...],
    *,
    input_data: str | None = None,
    user: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command inside a running container via ``docker exec``.

    Raises:
        DockerError: when Docker is unavailable or the exec fails.
    """
    docker = require_docker()
    argv = [docker, "exec", "--interactive"]
    if user:
        argv += ["--user", user]
    argv += [name, *command]
    try:
        return subprocess.run(
            argv,
            input=input_data,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        raise DockerError(
            f"docker exec in {name} failed (exit {exc.returncode}): {exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DockerError(f"docker exec in {name} timed out after 30s") from exc
    except OSError as exc:
        raise DockerError(f"failed to run docker exec: {exc}") from exc


def list_tether_containers() -> list[str]:
    """Return names of running containers whose name starts with ``tether-``."""
    docker = require_docker()
    result = subprocess.run(
        [docker, "ps", "--filter", "name=tether-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [
        n.strip()
        for n in result.stdout.splitlines()
        if n.strip() and n.strip().startswith("tether-")
    ]


def remove_image(image: str, *, force: bool = False) -> bool:
    """Remove *image* from the local store.

    Raises:
        DockerError: when Docker is unavailable.
    """
    docker = require_docker()
    command = [docker, "image", "rm"]
    if force:
        command.append("--force")
    command.append(image)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return result.returncode == 0
