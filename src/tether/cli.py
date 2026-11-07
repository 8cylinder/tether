"""Command line interface for tether."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import click
from rich.console import Console
from rich.markup import escape

from tether import __version__, completions, docker, ui
from tether.config import (
    Config,
    ConfigError,
    config_path,
    load_config,
    resolve_mounts,
)
from tether.docker import EXTRA_APPS
from tether.harnesses import AGENT_CHOICES, HARNESSES
from tether.util import (
    CONTAINER_WORKDIR,
    IMAGE_NAME,
    container_path_for,
    expand_host_path,
    host_uid_gid,
)


@dataclass
class AppContext:
    """Per-invocation state shared by every command."""

    config: Config
    color: str = "auto"

    def out(self) -> Console:
        return ui.console(mode=self.color)

    def err(self) -> Console:
        return ui.error_console(mode=self.color)


class _HelpOptions:
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        context_settings = dict(kwargs.pop("context_settings", {}) or {})
        context_settings.setdefault("help_option_names", ["-h", "--help"])
        kwargs["context_settings"] = context_settings
        super().__init__(*args, **kwargs)


class AppCommand(_HelpOptions, click.Command):
    pass


class AppGroup(_HelpOptions, click.Group):
    def command(self, *args: Any, **kwargs: Any) -> click.Command:  # noqa: ANN401
        kwargs.setdefault("cls", AppCommand)
        return cast(click.Command, super().command(*args, **kwargs))

    def group(self, *args: Any, **kwargs: Any) -> click.Group:  # noqa: ANN401
        kwargs.setdefault("cls", AppGroup)
        return cast(click.Group, super().group(*args, **kwargs))


_GLOBAL_OPTIONS = ("-h", "--help", "--version", "--config", "--completions")


class _DefaultRunGroup(AppGroup):
    """Run ``tether run`` when no subcommand is given.

    Arguments that are not subcommands are forwarded to ``run``, so
    ``tether --agent claude`` behaves like ``tether run --agent claude``.
    Root-level options such as ``--color`` are kept before the injected
    ``run``.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args:
            return super().parse_args(ctx, ["run"])

        first = args[0]
        if first in _GLOBAL_OPTIONS:
            return super().parse_args(ctx, args)
        if first in self.commands:
            return super().parse_args(ctx, args)
        if first == "--color":
            if len(args) == 2:
                return super().parse_args(ctx, [*args, "run"])
            if len(args) >= 3 and args[2] not in (
                *self.commands,
                *_GLOBAL_OPTIONS,
            ):
                return super().parse_args(
                    ctx, [args[0], args[1], "run", *args[2:]]
                )
            return super().parse_args(ctx, args)
        if first.startswith("--color="):
            rest = args[1:]
            if not rest:
                return super().parse_args(ctx, [*args, "run"])
            if rest[0] not in (*self.commands, *_GLOBAL_OPTIONS):
                return super().parse_args(ctx, [args[0], "run", *rest])
            return super().parse_args(ctx, args)
        return super().parse_args(ctx, ["run", *args])


def _write_completions(
    ctx: click.Context, param: click.Parameter, value: bool
) -> None:
    if not value or ctx.resilient_parsing:
        return

    if not isinstance(ctx.command, click.Group):
        raise click.ClickException("Completions require a command group.")
    try:
        path = completions.install_bash_completion(
            ctx.command, ctx.info_name or "tether", __version__
        )
    except OSError as exc:
        raise click.ClickException(
            f"Could not write completion script: {exc}"
        ) from exc

    click.echo("To enable completions in the current terminal, run:", err=True)
    click.echo(f"  source {path}", err=True)
    warning = completions.completion_warning(completions.bash_version())
    if warning:
        click.echo(f"warning: {warning}", err=True)
    ctx.exit()


def _print_config(
    ctx: click.Context, param: click.Parameter, value: bool
) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(str(config_path()))
    ctx.exit()


@click.group(name="tether", cls=_DefaultRunGroup)
@click.version_option(package_name="tether", prog_name="tether")
@click.option(
    "--color",
    type=click.Choice(["auto", "always", "never"], case_sensitive=False),
    default="auto",
    show_default=True,
    help="Control colored output.",
)
@click.option(
    "--completions",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_write_completions,
    help="Write bash completions and exit.",
)
@click.option(
    "--config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_config,
    help="Print the config file path and exit.",
)
@click.pass_context
def main(ctx: click.Context, color: str) -> None:
    """Run AI coding harnesses in a disposable Docker container at /workdir.

    With no subcommand, tether is equivalent to tether run.
    """
    try:
        config = load_config()
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    ctx.obj = AppContext(config=config, color=color)
    ctx.color = ui.color_setting(color)


def _require_docker() -> None:
    if not docker.docker_available():
        raise click.ClickException("docker was not found on PATH.")


def _require_image() -> None:
    if not docker.image_exists():
        raise click.ClickException("Image not found. Run 'tether build' first.")


def _show_skipped(obj: AppContext, skipped: list[tuple[str, str]]) -> None:
    if not skipped:
        return
    console = obj.err()
    for raw, reason in skipped:
        console.print(
            f"[yellow]warning:[/yellow] skipping mount "
            f"{escape(raw)} ({escape(reason)})"
        )


def _show_mounts(
    obj: AppContext,
    workdir: Path,
    mounts: list[tuple[str, str]],
) -> None:
    console = obj.out()
    console.print("[bold]Mounts:[/bold]")
    console.print(f"  {escape(str(workdir))} -> {CONTAINER_WORKDIR}")
    for host, container in mounts:
        console.print(f"  {escape(host)} -> {escape(container)}")


@main.command()  # ty: ignore[dynamic-function-decorator-return]
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
@click.pass_obj
def run(obj: AppContext, agent: str | None, workdir: Path | None) -> None:
    """Start the container and run an agent harness."""
    _require_docker()
    _require_image()

    config = obj.config
    agent = agent or config.default_agent
    harness = HARNESSES[agent]
    host_workdir = (workdir or Path.cwd()).resolve()

    mounted, skipped = resolve_mounts(config, agent)
    _show_skipped(obj, skipped)
    _show_mounts(obj, host_workdir, mounted)

    command = [*harness.command, *config.args_for(agent)]
    obj.out().print(
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


@main.command()  # ty: ignore[dynamic-function-decorator-return]
@click.option(
    "--update-software",
    is_flag=True,
    help=(
        "Ignore the build cache and pull the base image to upgrade "
        "all software."
    ),
)
@click.pass_obj
def build(obj: AppContext, update_software: bool) -> None:
    """Build (or rebuild) the container image."""
    _require_docker()
    uid, gid = host_uid_gid()
    console = obj.out()
    if update_software:
        console.print(
            "Updating all container software to the latest versions ..."
        )
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


@main.command()  # ty: ignore[dynamic-function-decorator-return]
@click.pass_obj
def info(obj: AppContext) -> None:
    """Show configuration, mounts and container status."""
    config = obj.config
    console = obj.out()

    console.print(f"[bold]config:[/bold]        {escape(str(config.path))}")
    console.print(f"[bold]default agent:[/bold] {escape(config.default_agent)}")

    version = docker.docker_version()
    if version:
        console.print(
            f"[bold]docker:[/bold]        [green]{escape(version)}[/green]"
        )
    else:
        console.print("[bold]docker:[/bold]        [red]not available[/red]")

    if version and docker.image_exists():
        image_state = "[green]present[/green]"
    elif version:
        image_state = "[yellow]not built[/yellow]"
    else:
        image_state = "[red]unknown, docker unavailable[/red]"
    console.print(f"[bold]image:[/bold]         {IMAGE_NAME} ({image_state})")
    console.print(
        "[bold]container:[/bold]     "
        "ephemeral (created per run, removed on exit)"
    )
    console.print("")
    console.print("[bold]harnesses:[/bold]")

    for name, harness in HARNESSES.items():
        marker = "[cyan]*[/cyan]" if name == config.default_agent else " "
        command = " ".join(harness.command)
        console.print(
            f" {marker} {name:<12} {escape(command):<8} "
            f"{escape(harness.description)}"
        )
        for raw in config.raw_mounts_for(name):
            host = expand_host_path(raw, config.path.parent)
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


@main.command()  # ty: ignore[dynamic-function-decorator-return]
@click.option(
    "--workdir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory to mount at /workdir. Defaults to the current directory.",
)
@click.pass_obj
def shell(obj: AppContext, workdir: Path | None) -> None:
    """Open an interactive shell in the container at /workdir."""
    _require_docker()
    _require_image()

    config = obj.config
    host_workdir = (workdir or Path.cwd()).resolve()
    mounted, skipped = resolve_mounts(config, config.default_agent)
    _show_skipped(obj, skipped)
    _show_mounts(obj, host_workdir, mounted)

    code = docker.run_container(IMAGE_NAME, host_workdir, mounted, ["bash"])
    raise SystemExit(code)


@main.command()  # ty: ignore[dynamic-function-decorator-return]
@click.pass_obj
def clean(obj: AppContext) -> None:
    """Remove the container image built by tether."""
    _require_docker()
    try:
        removed = docker.remove_image()
    except docker.DockerError as exc:
        raise click.ClickException(str(exc)) from exc
    if removed:
        obj.out().print(f"[green]Removed[/green] {IMAGE_NAME}.")
    else:
        obj.out().print(
            f"[yellow]Nothing to remove[/yellow] ({IMAGE_NAME} not found)."
        )


if __name__ == "__main__":  # pragma: no cover
    main()
