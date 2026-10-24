"""Command line interface for tether."""

from __future__ import annotations

import textwrap
from pathlib import Path

import click
from rich.markup import escape

from tether import __version__, completion, docker, ui
from tether.config import ConfigError, config_path, load_config, resolve_mounts
from tether.docker import EXTRA_APPS
from tether.harnesses import AGENT_CHOICES, HARNESSES
from tether.util import (
    CONTAINER_WORKDIR,
    IMAGE_NAME,
    container_path_for,
    expand_host_path,
    host_uid_gid,
)


def _write_completions(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return

    try:
        path = completion.write_bash_completion(main)
    except OSError as exc:
        raise click.ClickException(f"Could not write completion script: {exc}") from exc
    console = ui.console()
    console.print(f"[green]Wrote[/green] {escape(str(path))}")
    console.print("To enable completions in the current terminal, run:")
    console.print(f"  [cyan]source {escape(str(path))}[/cyan]")

    warning = completion.completion_warning(completion.bash_version())
    if warning:
        ui.error_console().print(f"[yellow]warning:[/yellow] {escape(warning)}")
    ctx.exit()


def _print_config(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return

    ui.console().print(str(config_path()), markup=False)
    ctx.exit()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="tether")
@click.option(
    "--completions",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_write_completions,
    help="Write bash completions to the XDG data directory and exit.",
)
@click.option(
    "--config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_config,
    help="Print the config file path and exit.",
)
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
    if not skipped:
        return
    console = ui.error_console()
    for raw, reason in skipped:
        console.print(f"[yellow]warning:[/yellow] skipping mount {escape(raw)} ({escape(reason)})")


def _show_mounts(workdir: Path, mounts: list[tuple[str, str]]) -> None:
    console = ui.console()
    console.print("[bold]Mounts:[/bold]")
    console.print(f"  {escape(str(workdir))} -> {CONTAINER_WORKDIR}")
    for host, container in mounts:
        console.print(f"  {escape(host)} -> {escape(container)}")


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

    mounted, skipped = resolve_mounts(config, agent)
    _show_skipped(skipped)
    _show_mounts(host_workdir, mounted)

    command = [*harness.command, *config.args_for(agent)]
    ui.console().print(
        f"Running [cyan]{escape(harness.description)}[/cyan] in "
        f"{escape(str(host_workdir))} (mounted at /workdir)."
    )
    code = docker.run_container(
        IMAGE_NAME,
        host_workdir,
        mounted,
        command,
    )
    raise SystemExit(code)


@main.command()
@click.option(
    "--update-software",
    is_flag=True,
    help="Ignore the build cache and pull the base image to upgrade all software.",
)
def build(update_software: bool) -> None:
    """Build (or rebuild) the container image."""
    _require_docker()
    uid, gid = host_uid_gid()
    console = ui.console()
    if update_software:
        console.print("Updating all container software to the latest versions ...")
    console.print(f"Building {IMAGE_NAME} (UID={uid}, GID={gid}) ...")
    try:
        docker.build_image(
            IMAGE_NAME,
            uid=uid,
            gid=gid,
            update_software=update_software,
        )
    except docker.DockerError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"[green]Built[/green] {IMAGE_NAME}.")


@main.command()
def info() -> None:
    """Show configuration, mounts and container status."""
    config = _load_config()
    console = ui.console()

    console.print(f"[bold]config:[/bold]        {escape(str(config.path))}")
    console.print(f"[bold]default agent:[/bold] {escape(config.default_agent)}")

    version = docker.docker_version()
    if version:
        console.print(f"[bold]docker:[/bold]        [green]{escape(version)}[/green]")
    else:
        console.print("[bold]docker:[/bold]        [red]not available[/red]")

    if version and docker.image_exists():
        image_state = "[green]present[/green]"
    elif version:
        image_state = "[yellow]not built[/yellow]"
    else:
        image_state = "[red]unknown, docker unavailable[/red]"
    console.print(f"[bold]image:[/bold]         {IMAGE_NAME} ({image_state})")
    console.print("[bold]container:[/bold]     ephemeral (created per run, removed on exit)")
    console.print("")
    console.print("[bold]harnesses:[/bold]")

    for name, harness in HARNESSES.items():
        marker = "[cyan]*[/cyan]" if name == config.default_agent else " "
        command = " ".join([*harness.command, *config.args_for(name)])
        console.print(f" {marker} {name:<12} {escape(command):<8} {escape(harness.description)}")
        for raw in config.raw_mounts_for(name):
            host = expand_host_path(raw)
            label = "ok" if host.exists() else "missing"
            color = "green" if host.exists() else "yellow"
            console.print(
                f"       [{color}]{label:^7}[/{color}] {escape(raw)}  ->  "
                f"{escape(container_path_for(host))}"
            )

    console.print("")
    console.print("[bold]extra installed apps:[/bold]")
    console.print(
        textwrap.fill(
            ", ".join(EXTRA_APPS),
            width=76,
            initial_indent="  ",
            subsequent_indent="  ",
        ),
        markup=False,
    )


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
    mounted, skipped = resolve_mounts(config, config.default_agent)
    _show_skipped(skipped)
    _show_mounts(host_workdir, mounted)

    code = docker.run_container(IMAGE_NAME, host_workdir, mounted, ["bash"])
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
        ui.console().print(f"[green]Removed[/green] {IMAGE_NAME}.")
    else:
        ui.console().print(f"[yellow]Nothing to remove[/yellow] ({IMAGE_NAME} not found).")


if __name__ == "__main__":  # pragma: no cover
    main()
