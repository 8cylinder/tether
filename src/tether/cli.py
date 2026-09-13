"""Command line interface for tether."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
from rich.console import Console

from tether import __version__
from tether.config import default_config_path, load_config, write_default_config
from tether.platform import default_profile_name, find_docker, host_info

console = Console()

EXIT_NOT_IMPLEMENTED = 2


def _print_version(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    console.print(f"tether {__version__}")
    ctx.exit()


@click.group(
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Run AI coding agents in a container confined to a project directory.",
)
@click.option(
    "--version",
    is_flag=True,
    callback=_print_version,
    expose_value=False,
    is_eager=True,
    help="Show the version and exit.",
)
def app() -> None:
    """tether command group."""


@app.command()
@click.option("--force", is_flag=True, help="Overwrite an existing config.")
@click.option(
    "--path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Config file to write.",
)
def init(force: bool, path: Path | None) -> None:
    """Create the default configuration file."""
    try:
        target = write_default_config(path, force=force)
    except FileExistsError as exc:
        console.print(f"[yellow]Config already exists:[/] {exc.args[0]}")
        console.print("Use --force to overwrite.")
        raise click.exceptions.Exit(code=1) from exc
    console.print(f"[green]Wrote[/] {target}")


@app.command()
def doctor() -> None:
    """Report host, tooling, and configuration status."""
    info = host_info()
    profile_name = default_profile_name()
    config_path = default_config_path()

    console.print(f"tether {__version__}")
    console.print(f"platform: {info.system} ({info.machine})")
    console.print(f"uid/gid:  {info.uid}:{info.gid}")
    console.print(f"config:   {config_path} ({'found' if config_path.exists() else 'missing'})")

    docker = find_docker()
    if docker is None:
        console.print("docker:   [red]not found[/]")
    else:
        version = _docker_version(docker)
        console.print(f"docker:   {docker} ({version})")

    try:
        config = load_config()
    except ValueError as exc:
        console.print(f"[red]config error:[/] {exc}")
        raise click.exceptions.Exit(code=1) from exc

    profile = config.profile_for(profile_name)
    console.print(f"profile:  {profile_name} -> agent={profile.agent}")


@app.command()
def run() -> None:
    """Launch a harness inside the jail (not implemented yet)."""
    console.print("[yellow]run is not implemented yet[/] (milestone 2/3).")
    raise click.exceptions.Exit(code=EXIT_NOT_IMPLEMENTED)


@app.command()
def shell() -> None:
    """Open a shell inside the jail (not implemented yet)."""
    console.print("[yellow]shell is not implemented yet[/] (milestone 2/3).")
    raise click.exceptions.Exit(code=EXIT_NOT_IMPLEMENTED)


@app.command()
def clean() -> None:
    """Remove tether images and volumes (not implemented yet)."""
    console.print("[yellow]clean is not implemented yet[/] (milestone 5).")
    raise click.exceptions.Exit(code=EXIT_NOT_IMPLEMENTED)


def _docker_version(docker: str) -> str:
    try:
        result = subprocess.run(
            [docker, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if result.returncode != 0:
        return "unavailable"
    return result.stdout.strip() or "unknown"


if __name__ == "__main__":
    app()
