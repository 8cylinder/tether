"""Thin wrappers around the ``docker`` CLI."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from importlib import resources
from pathlib import Path

from tether.util import CONTAINER_WORKDIR, IMAGE_NAME

# Command-line tools installed in the image on top of the base image. The AI
# harnesses have their own section in ``tether info``.
EXTRA_APPS: tuple[str, ...] = (
    "bash",
    "build-essential",
    "ca-certificates",
    "curl",
    "fd-find",
    "git",
    "gnupg",
    "jq",
    "less",
    "libsecret-1-0",
    "make",
    "nano",
    "openssh-client",
    "pipx",
    "procps",
    "python3",
    "python3-pip",
    "python3-venv",
    "ripgrep",
    "sudo",
    "tmux",
    "unzip",
    "uv",
    "vim",
    "wget",
    "zip",
    "zsh",
)


class DockerError(RuntimeError):
    """Raised when a docker command fails."""


def docker_available() -> bool:
    return shutil.which("docker") is not None


def docker_version() -> str | None:
    """Return the docker server version, or ``None`` if unavailable."""
    if not docker_available():
        return None
    result = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def image_exists(image: str = IMAGE_NAME) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _write_dockerfile(destination: Path) -> None:
    source = resources.files("tether").joinpath("docker").joinpath("Dockerfile")
    destination.write_bytes(source.read_bytes())


def build_image(
    image: str = IMAGE_NAME,
    *,
    uid: int,
    gid: int,
    update_software: bool = False,
) -> None:
    """Build the container image from the bundled Dockerfile.

    With ``update_software`` the build cache is bypassed and the base image is
    pulled so apt packages, npm harnesses and the Antigravity CLI are all
    upgraded to the latest available versions.
    """
    with tempfile.TemporaryDirectory(prefix="tether-build-") as tmp:
        context = Path(tmp)
        _write_dockerfile(context / "Dockerfile")
        command = [
            "docker",
            "build",
            "--tag",
            image,
        ]
        if update_software:
            command += ["--no-cache", "--pull"]
        command += [
            "--build-arg",
            f"UID={uid}",
            "--build-arg",
            f"GID={gid}",
            str(context),
        ]
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            raise DockerError(f"docker build failed with exit code {result.returncode}")


def run_container(
    image: str,
    workdir: Path,
    mounts: list[tuple[str, str]],
    command: list[str],
) -> int:
    """Run a one-off interactive container with the project and mounts attached."""
    args = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--tty",
        "--hostname",
        "tether",
        "--env",
        "TERM",
        "--volume",
        f"{workdir}:{CONTAINER_WORKDIR}",
        "--workdir",
        CONTAINER_WORKDIR,
    ]
    for host, container in mounts:
        args += ["--volume", f"{host}:{container}"]
    args.append(image)
    args += command

    result = subprocess.run(args, check=False)
    return result.returncode


def remove_image(image: str = IMAGE_NAME) -> bool:
    """Force-remove the image. Returns ``True`` if an image was removed."""
    if not image_exists(image):
        return False
    result = subprocess.run(
        ["docker", "image", "rm", "--force", image],
        check=False,
    )
    if result.returncode != 0:
        raise DockerError(f"failed to remove image {image}")
    return True
