"""Command line interface for tether."""

from __future__ import annotations

from pathlib import Path

import click

from tether import __version__, docker
from tether.config import ConfigError, load_config, resolve_mounts
from tether.harnesses import AGENT_CHOICES, HARNESSES
from tether.util import IMAGE_NAME, container_path_for, expand_host_path, host_uid_gid


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="tether")
def main() -> None:
    """Run AI coding harnesses in a disposable Docker container at /workdir."""


def _load_config():
    try:
        return load_config()
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


def _require_docker() -> None:
    if not docker.docker_available():
        raise click.ClickException("docker was not found on PATH.")


def _require_image() -> None:
    if not docker.image_exists():
        raise click.ClickException("Image not found. Run 'tether build' first.")


def _show_skipped(skipped: list[tuple[str, str]]) -> None:
    for raw, reason in skipped:
        click.echo(f"warning: skipping mount {raw} ({reason})", err=True)


@main.command()
@click.option(
    "--agent",
    type=click.Choice(AGENT_CHOICES),
    default=None,
    help="Harness to run. Defaults to the harness set in the config file.",
)
@click.option(
    "--workdir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory to mount at /workdir. Defaults to the current directory.",
)
def run(agent: str | None, workdir: Path | None) -> None:
    """Start the container and run an agent harness."""
    _require_docker()
    _require_image()

    config = _load_config()
    agent = agent or config.default_agent
    harness = HARNESSES[agent]
    host_workdir = (workdir or Path.cwd()).resolve()

    mounts, skipped = resolve_mounts(config, agent)
    _show_skipped(skipped)

    click.echo(f"Running {harness.description} in {host_workdir} (mounted at /workdir).")
    code = docker.run_container(
        IMAGE_NAME,
        host_workdir,
        mounts,
        [harness.command],
    )
    raise SystemExit(code)


@main.command()
def build() -> None:
    """Build (or rebuild) the container image."""
    _require_docker()
    uid, gid = host_uid_gid()
    click.echo(f"Building {IMAGE_NAME} (UID={uid}, GID={gid}) ...")
    try:
        docker.build_image(IMAGE_NAME, uid=uid, gid=gid)
    except docker.DockerError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Built {IMAGE_NAME}.")


@main.command()
def info() -> None:
    """Show configuration, mounts and container status."""
    config = _load_config()

    click.echo(f"config:        {config.path}")
    click.echo(f"default agent: {config.default_agent}")

    version = docker.docker_version()
    click.echo(f"docker:        {version if version else 'not available'}")
    if version:
        image_state = "present" if docker.image_exists() else "not built"
    else:
        image_state = "unknown (docker unavailable)"
    click.echo(f"image:         {IMAGE_NAME} ({image_state})")
    click.echo("container:     ephemeral (created per run, removed on exit)")
    click.echo("")
    click.echo("harnesses:")

    for name, harness in HARNESSES.items():
        marker = "*" if name == config.default_agent else " "
        click.echo(f" {marker} {name:<12} {harness.command:<8} {harness.description}")
        for raw in config.raw_mounts_for(name):
            host = expand_host_path(raw)
            status = "ok" if host.exists() else "missing"
            click.echo(f"       [{status:^7}] {raw}  ->  {container_path_for(host)}")


@main.command()
@click.option(
    "--workdir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory to mount at /workdir. Defaults to the current directory.",
)
def shell(workdir: Path | None) -> None:
    """Open an interactive shell in the container at /workdir."""
    _require_docker()
    _require_image()

    config = _load_config()
    host_workdir = (workdir or Path.cwd()).resolve()
    mounts, skipped = resolve_mounts(config, config.default_agent)
    _show_skipped(skipped)

    code = docker.run_container(IMAGE_NAME, host_workdir, mounts, ["bash"])
    raise SystemExit(code)


@main.command()
def clean() -> None:
    """Remove the container image built by tether."""
    _require_docker()
    try:
        removed = docker.remove_image()
    except docker.DockerError as exc:
        raise click.ClickException(str(exc)) from exc
    if removed:
        click.echo(f"Removed {IMAGE_NAME}.")
    else:
        click.echo(f"Nothing to remove ({IMAGE_NAME} not found).")


if __name__ == "__main__":  # pragma: no cover
    main()
