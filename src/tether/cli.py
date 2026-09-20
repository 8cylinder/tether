"""Command line interface for tether."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from tether import __version__
from tether.agents import AGENTS, get_agent
from tether.auth import (
    AuthError,
    AwsCredentials,
    aws_credential_env,
    aws_credentials_ini,
    collect_env,
    env_file,
    opencode_auth_env,
    resolve_aws_credentials,
    stage_aws_credentials,
)
from tether.config import (
    Config,
    EnvConfig,
    default_config_path,
    load_config,
    write_default_config,
)
from tether.docker import (
    DockerError,
    RunConfig,
    build_image,
    build_run_command,
    container_running,
    exec_in_container,
    image_exists,
    list_tether_containers,
    remove_image,
    resolve_agent_build_args,
    run_container,
)
from tether.mounts import (
    CONTAINER_AWS_CREDENTIALS,
    ContainerMount,
    MountError,
    build_mounts,
    claude_config_mounts,
    has_git,
    opencode_config_mounts,
    opencode_state_mounts,
    resolve_project,
)
from tether.platform import default_profile_name, find_docker, host_info, state_dir
from tether.staging import StagedFile

console = Console()

LINUX = "linux"


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
    console.print(f"image:    {config.image} ({_image_status(config.image)})")
    _print_env_status(profile.env)

    if profile.aws_credential_export is not None:
        export = profile.aws_credential_export
        console.print(
            f"aws:      profile={export.profile} region={export.region} [dim](credential export)[/]"
        )
    elif "CLAUDE_CODE_USE_BEDROCK" in profile.env.static and "AWS_PROFILE" in profile.env.static:
        console.print(
            "[yellow]hint:[/] migrate to [bold]aws_credential_export[/] "
            "in your profile for automatic SSO credential handling"
        )


@app.command()
@click.option("--force", is_flag=True, help="Rebuild even if the image already exists.")
@click.option(
    "--pinned",
    is_flag=True,
    help="Use the versions pinned in the Dockerfile instead of the latest releases.",
)
def build(force: bool, pinned: bool) -> None:
    """Build the container image used by the jail."""
    config = _load_config()

    if not force and _image_present(config.image):
        console.print(f"{config.image} already exists (use --force to rebuild).")
        return

    build_args = _agent_build_args(pinned=pinned)
    console.print(f"Building [bold]{config.image}[/] ...")
    try:
        result = build_image(config.image, force=force, build_args=build_args)
    except DockerError as exc:
        console.print(f"[red]error:[/] {exc}")
        raise click.exceptions.Exit(code=1) from exc

    if result.built:
        console.print(f"[green]Built[/] {result.image}")
    else:
        console.print(f"{result.image} already exists (use --force to rebuild).")


@app.command()
@click.option(
    "--agent",
    type=click.Choice(sorted(AGENTS)),
    default=None,
    help="Harness to launch (defaults to the profile's agent).",
)
@click.option(
    "--project",
    "-C",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Project directory to confine the agent to (default: cwd).",
)
@click.option("--profile", default=None, help="Config profile to use (default: platform name).")
@click.option("--dry-run", is_flag=True, help="Print the docker command without running it.")
@click.option("--no-build", is_flag=True, help="Fail instead of building a missing image.")
@click.option(
    "--continue",
    "continue_session",
    is_flag=True,
    help="Resume the most recent session for the project (opencode only).",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run(
    agent: str | None,
    project: Path | None,
    profile: str | None,
    dry_run: bool,
    no_build: bool,
    continue_session: bool,
    args: tuple[str, ...],
) -> None:
    """Launch a harness inside the jail."""
    _launch(
        agent=agent,
        project=project,
        profile=profile,
        dry_run=dry_run,
        no_build=no_build,
        continue_session=continue_session,
        command=None,
        args=args,
        named=True,
    )


@app.command()
@click.option(
    "--project",
    "-C",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Project directory to confine the shell to (default: cwd).",
)
@click.option("--profile", default=None, help="Config profile to use (default: platform name).")
@click.option("--dry-run", is_flag=True, help="Print the docker command without running it.")
@click.option("--no-build", is_flag=True, help="Fail instead of building a missing image.")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def shell(
    project: Path | None,
    profile: str | None,
    dry_run: bool,
    no_build: bool,
    args: tuple[str, ...],
) -> None:
    """Open a shell inside the jail."""
    _launch(
        agent=None,
        project=project,
        profile=profile,
        dry_run=dry_run,
        no_build=no_build,
        command=("bash",),
        args=args,
        named=False,
    )


@app.command()
@click.option("--yes", "-y", is_flag=True, help="Do not prompt for confirmation.")
@click.option("--force", is_flag=True, help="Force removal of the image.")
@click.option(
    "--state",
    is_flag=True,
    help="Remove persisted agent session state instead of the image.",
)
def clean(yes: bool, force: bool, state: bool) -> None:
    """Remove the configured container image or persisted session state."""
    if state:
        _clean_state(yes)
        return

    config = _load_config()

    if not _image_present(config.image):
        console.print(f"{config.image} is not present; nothing to remove.")
        return

    if not yes and not click.confirm(f"Remove image {config.image}?"):
        console.print("Aborted.")
        raise click.exceptions.Exit(code=1)

    try:
        removed = remove_image(config.image, force=force)
    except DockerError as exc:
        console.print(f"[red]error:[/] {exc}")
        raise click.exceptions.Exit(code=1) from exc

    if removed:
        console.print(f"[green]Removed[/] {config.image}")
    else:
        console.print(f"[red]Failed to remove[/] {config.image}")
        raise click.exceptions.Exit(code=1)


def _clean_state(yes: bool) -> None:
    """Remove tether's persisted per-project session state."""
    root = state_dir() / "sessions"
    if not root.exists():
        console.print("No persisted session state found.")
        return
    if not yes and not click.confirm(f"Remove persisted session state at {root}?"):
        console.print("Aborted.")
        raise click.exceptions.Exit(code=1)
    shutil.rmtree(root, ignore_errors=True)
    if root.exists():
        console.print(f"[red]Failed to remove[/] {root}")
        raise click.exceptions.Exit(code=1)
    console.print(f"[green]Removed[/] {root}")


@app.command()
@click.argument("container", required=False, default=None)
@click.option("--profile", default=None, help="Config profile to use (default: platform name).")
def refresh(container: str | None, profile: str | None) -> None:
    """Refresh AWS credentials in a running container."""
    config = _load_config()
    profile_name = profile or default_profile_name()
    profile_config = config.profile_for(profile_name)

    if profile_config.aws_credential_export is None:
        console.print("[red]error:[/] no aws_credential_export configured in this profile")
        raise click.exceptions.Exit(code=1)

    if container is None:
        try:
            containers = list_tether_containers()
        except DockerError as exc:
            console.print(f"[red]error:[/] {exc}")
            raise click.exceptions.Exit(code=1) from exc
        if not containers:
            console.print("[red]error:[/] no running tether containers found")
            raise click.exceptions.Exit(code=1)
        if len(containers) == 1:
            container = containers[0]
        else:
            console.print("Running tether containers:")
            for name in containers:
                console.print(f"  {name}")
            console.print("\nSpecify a container: tether refresh <name>")
            raise click.exceptions.Exit(code=1)

    try:
        creds = resolve_aws_credentials(profile_config.aws_credential_export)
    except AuthError as exc:
        console.print(f"[red]auth error:[/] {exc}")
        raise click.exceptions.Exit(code=1) from exc

    info = host_info()
    user = f"{info.uid}:{info.gid}" if info.system == LINUX else None

    try:
        exec_in_container(
            container,
            (
                "sh",
                "-c",
                f"mkdir -p /tmp/tether-home/.aws && cat > {CONTAINER_AWS_CREDENTIALS}",
            ),
            input_data=aws_credentials_ini(creds),
            user=user,
        )
    except DockerError as exc:
        console.print(f"[red]error:[/] {exc}")
        raise click.exceptions.Exit(code=1) from exc

    _print_expiry(creds)
    console.print(f"[green]Credentials refreshed[/] in container [bold]{container}[/]")


def _launch(
    *,
    agent: str | None,
    project: Path | None,
    profile: str | None,
    dry_run: bool,
    no_build: bool,
    command: tuple[str, ...] | None,
    args: tuple[str, ...],
    continue_session: bool = False,
    named: bool = True,
) -> None:
    config = _load_config()
    profile_name = profile or default_profile_name()
    profile_config = config.profile_for(profile_name)
    agent_name = agent or profile_config.agent

    resume_flag: str | None = None
    if command is None:
        try:
            spec = get_agent(agent_name)
        except KeyError as exc:
            console.print(f"[red]unknown agent:[/] {agent_name}")
            raise click.exceptions.Exit(code=1) from exc
        base_command = spec.command
        resume_flag = spec.resume_flag
    else:
        base_command = command

    if continue_session:
        if resume_flag is None:
            console.print(f"[red]error:[/] {agent_name} does not support --continue")
            raise click.exceptions.Exit(code=1)
        base_command = (*base_command, resume_flag)

    try:
        project_dir = resolve_project(project or Path.cwd())
        mounts = build_mounts(project_dir, extra=profile_config.mounts)
    except MountError as exc:
        console.print(f"[red]mount error:[/] {exc}")
        raise click.exceptions.Exit(code=1) from exc

    staged_files: list[StagedFile] = []
    opencode_env: dict[str, str] = {}
    try:
        if agent_name == "claude":
            claude_mounts, claude_temps = claude_config_mounts()
            mounts.extend(claude_mounts)
            staged_files.extend(claude_temps)
        elif agent_name == "opencode":
            opencode_mounts, opencode_temps, opencode_env = opencode_config_mounts()
            mounts.extend(opencode_mounts)
            staged_files.extend(opencode_temps)
            mounts.extend(opencode_state_mounts(project_dir))

        aws_env: dict[str, str] = {}
        container_name: str | None = None
        if profile_config.aws_credential_export is not None:
            try:
                creds = resolve_aws_credentials(profile_config.aws_credential_export)
            except AuthError as exc:
                console.print(f"[red]auth error:[/] {exc}")
                raise click.exceptions.Exit(code=1) from exc
            aws_env = aws_credential_env(creds)
            creds_file = stage_aws_credentials(creds)
            staged_files.append(creds_file)
            mounts.append(
                ContainerMount(source=creds_file.path, target=CONTAINER_AWS_CREDENTIALS, mode="rw")
            )
            _print_expiry(creds)
            if named:
                candidate = _container_name(project or Path.cwd())
                with suppress(DockerError):
                    if not container_running(candidate):
                        container_name = candidate

        if not _ensure_image(config.image, no_build=no_build, dry_run=dry_run):
            raise click.exceptions.Exit(code=1)

        if not has_git(project_dir):
            console.print(
                "[yellow]warning:[/] project is not a git repository; "
                "changes cannot be recovered from git."
            )

        try:
            env_values = collect_env(profile_config.env)
        except AuthError as exc:
            console.print(f"[red]auth error:[/] {exc}")
            raise click.exceptions.Exit(code=1) from exc
        env_values.update(aws_env)
        if agent_name == "claude":
            env_values["DISABLE_AUTOUPDATER"] = "1"
        elif agent_name == "opencode":
            env_values["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
            permission = {"edit": "ask", "bash": "allow"}
            env_values["OPENCODE_CONFIG_CONTENT"] = json.dumps(
                {
                    "$schema": "https://opencode.ai/config.json",
                    "permission": permission,
                    "agent": {
                        "normal": {"permission": permission},
                        "build": {"permission": permission},
                    },
                }
            )
            env_values.update(opencode_env)
            env_values.update(opencode_auth_env())

        full_command = (*base_command, *args)

        info = host_info()
        user = f"{info.uid}:{info.gid}" if info.system == LINUX else None

        run_config = RunConfig(
            image=config.image,
            command=full_command,
            mounts=tuple(mounts),
            user=user,
            name=container_name,
            memory=profile_config.resources.memory,
            cpus=profile_config.resources.cpus,
            pids_limit=profile_config.resources.pids_limit,
            tty=sys.stdin.isatty() and sys.stdout.isatty(),
        )

        docker = find_docker() or "docker"

        if dry_run:
            plan_config = replace(run_config, env_file="<env-file>") if env_values else run_config
            docker_command = build_run_command(plan_config, docker=docker)
            _print_plan(agent_name, project_dir, mounts, sorted(env_values), docker_command)
            return

        try:
            with env_file(env_values) as path:
                active_config = replace(run_config, env_file=str(path) if path else None)
                code = run_container(active_config)
        except (DockerError, AuthError) as exc:
            console.print(f"[red]error:[/] {exc}")
            raise click.exceptions.Exit(code=1) from exc
        raise click.exceptions.Exit(code=code)
    except MountError as exc:
        console.print(f"[red]mount error:[/] {exc}")
        raise click.exceptions.Exit(code=1) from exc
    finally:
        for staged in staged_files:
            staged.cleanup()


def _load_config() -> Config:
    try:
        return load_config()
    except ValueError as exc:
        console.print(f"[red]config error:[/] {exc}")
        raise click.exceptions.Exit(code=1) from exc


def _agent_build_args(*, pinned: bool = False) -> dict[str, str]:
    """Resolve latest agent CLI versions for the image build.

    Falls back to the Dockerfile pins (no build args) when resolution fails.
    """
    if pinned:
        return {}
    try:
        build_args = resolve_agent_build_args()
    except DockerError as exc:
        console.print(f"[yellow]warning:[/] {exc}; using pinned versions from the Dockerfile")
        return {}
    if build_args:
        summary = ", ".join(
            f"{name.removesuffix('_VERSION').lower()}={version}"
            for name, version in sorted(build_args.items())
        )
        console.print(f"Resolved latest agent versions: {summary}")
    return build_args


def _ensure_image(image: str, *, no_build: bool, dry_run: bool) -> bool:
    if _image_present(image):
        return True
    if dry_run or no_build:
        console.print(f"[yellow]image not built:[/] {image}. Run 'tether build'.")
        return not no_build
    build_args = _agent_build_args()
    console.print(f"Building [bold]{image}[/] ...")
    try:
        build_image(image, build_args=build_args)
    except DockerError as exc:
        console.print(f"[red]error:[/] {exc}")
        return False
    return True


def _image_present(image: str) -> bool:
    try:
        return image_exists(image)
    except DockerError:
        return False


def _image_status(image: str) -> str:
    return "present" if _image_present(image) else "missing"


def _print_env_status(env_config: EnvConfig) -> None:
    for name in sorted(env_config.static):
        console.print(f"env:      {name} [dim](static)[/]")
    for name in sorted(env_config.passthrough):
        state = "[green]set[/]" if name in os.environ else "[red]missing[/]"
        console.print(f"env:      {name} {state}")


def _print_plan(
    agent_name: str,
    project_dir: Path,
    mounts: list[ContainerMount],
    env_names: list[str],
    docker_command: list[str],
) -> None:
    console.print(f"agent:   {agent_name}")
    console.print(f"project: {project_dir}")
    if env_names:
        console.print(f"env:     {', '.join(env_names)} (values redacted)")
    table = Table("source", "target", "mode")
    for mount in mounts:
        table.add_row(str(mount.source), mount.target, mount.mode)
    console.print(table)
    console.print("[bold]docker command:[/]")
    console.print(shlex.join(docker_command))


def _print_expiry(creds: AwsCredentials) -> None:
    if creds.expiration is None:
        return
    remaining = creds.expiration - datetime.now(UTC)
    seconds = int(remaining.total_seconds())
    if seconds <= 0:
        console.print("[yellow]warning:[/] AWS credentials are already expired")
        return
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    console.print(f"[dim]AWS credentials expire in {hours}h {minutes}m[/]")


_CONTAINER_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _container_name(project: Path) -> str:
    resolved = project.resolve()
    digest = hashlib.sha256(str(resolved).encode()).hexdigest()[:8]
    slug = _CONTAINER_NAME_UNSAFE.sub("-", resolved.name).strip("-.") or "project"
    return f"tether-{slug}-{digest}"


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
