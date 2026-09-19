"""Credential handling for the jail.

Secrets are forwarded with ``--env-file`` rather than ``--env KEY=VALUE`` so they
never appear in the host process list. The file is written with mode 0600 and
removed as soon as the container exits.

AWS Bedrock credentials are exported from the host via
``aws configure export-credentials`` and injected as environment variables.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tether.config import AwsCredentialExport, EnvConfig
from tether.staging import READ_WRITE_MODE, StagedFile, stage

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AuthError(ValueError):
    """Raised when credentials cannot be resolved or formatted."""


def collect_env(
    env_config: EnvConfig,
    host_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Merge static values with the host values named by ``passthrough``.

    Raises:
        AuthError: when a passthrough variable is not set on the host.
    """
    source = host_env if host_env is not None else os.environ
    missing = [name for name in env_config.passthrough if name not in source]
    if missing:
        raise AuthError("required environment variables are not set: " + ", ".join(sorted(missing)))

    resolved: dict[str, str] = dict(env_config.static)
    for name in env_config.passthrough:
        resolved[name] = source[name]
    return resolved


def _format_env(env: Mapping[str, str]) -> str:
    lines: list[str] = []
    for key, value in env.items():
        if not _ENV_NAME.match(key):
            raise AuthError(f"invalid environment variable name: {key!r}")
        if "\n" in value or "\r" in value or "\x00" in value:
            raise AuthError(f"environment value for {key} contains an unsupported character")
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def write_env_file(env: Mapping[str, str]) -> Path:
    """Write *env* to a fresh mode-0600 file and return its path."""
    handle, name = tempfile.mkstemp(prefix="tether-env-", suffix=".env")
    path = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(_format_env(env))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


@contextmanager
def env_file(env: Mapping[str, str]) -> Iterator[Path | None]:
    """Yield a temporary env-file path for *env*, cleaning it up afterwards.

    Yields ``None`` when *env* is empty.
    """
    if not env:
        yield None
        return
    path = write_env_file(env)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# AWS credential export
# ---------------------------------------------------------------------------

_REQUIRED_AWS_KEYS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")


@dataclass(frozen=True, slots=True)
class AwsCredentials:
    """Temporary STS credentials exported from the host AWS CLI."""

    access_key_id: str
    secret_access_key: str
    session_token: str
    region: str
    expiration: datetime | None = None


def find_aws_cli() -> str:
    """Return the path to the ``aws`` CLI.

    Raises:
        AuthError: when the CLI is not on ``PATH``.
    """
    path = shutil.which("aws")
    if path is None:
        raise AuthError("AWS CLI is required for credential export but was not found on PATH")
    return path


def _parse_export_env(output: str) -> dict[str, str]:
    """Parse ``export KEY=VALUE`` lines into a dict."""
    result: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, sep, value = line.partition("=")
        if not sep:
            continue
        result[key] = value
    return result


def export_aws_credentials(profile: str, region: str) -> AwsCredentials:
    """Export temporary credentials from the host AWS CLI.

    Raises:
        AuthError: when the export fails or required keys are missing.
    """
    aws = find_aws_cli()
    try:
        result = subprocess.run(
            [aws, "configure", "export-credentials", "--profile", profile, "--format", "env"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        raise AuthError(
            f"aws configure export-credentials failed (exit {exc.returncode}): {stderr}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AuthError("aws configure export-credentials timed out after 30s") from exc

    env = _parse_export_env(result.stdout)

    missing = [k for k in _REQUIRED_AWS_KEYS if not env.get(k)]
    if missing:
        raise AuthError(
            "credential export did not produce required keys: " + ", ".join(sorted(missing))
        )

    expiration: datetime | None = None
    raw_exp = env.get("AWS_CREDENTIAL_EXPIRATION")
    if raw_exp:
        with suppress(ValueError):
            expiration = datetime.fromisoformat(raw_exp.replace("Z", "+00:00"))

    return AwsCredentials(
        access_key_id=env["AWS_ACCESS_KEY_ID"],
        secret_access_key=env["AWS_SECRET_ACCESS_KEY"],
        session_token=env["AWS_SESSION_TOKEN"],
        region=region,
        expiration=expiration,
    )


def run_sso_login(profile: str) -> None:
    """Run ``aws sso login`` interactively for *profile*.

    Raises:
        AuthError: when the login fails.
    """
    aws = find_aws_cli()
    try:
        result = subprocess.run(
            [aws, "sso", "login", "--profile", profile],
            check=False,
        )
    except OSError as exc:
        raise AuthError(f"failed to run aws sso login: {exc}") from exc
    if result.returncode != 0:
        raise AuthError(f"aws sso login failed (exit {result.returncode})")


def resolve_aws_credentials(export_config: AwsCredentialExport) -> AwsCredentials:
    """Export credentials, running SSO login first if needed.

    Raises:
        AuthError: when credentials cannot be obtained.
    """
    try:
        return export_aws_credentials(export_config.profile, export_config.region)
    except AuthError:
        pass

    run_sso_login(export_config.profile)
    return export_aws_credentials(export_config.profile, export_config.region)


def aws_credential_env(creds: AwsCredentials) -> dict[str, str]:
    """Return non-secret AWS env vars (region, pager) for the container.

    Credential keys are deliberately excluded so they can be delivered via
    the credentials file, which ``tether refresh`` can overwrite at runtime.
    """
    return {
        "AWS_REGION": creds.region,
        "AWS_DEFAULT_REGION": creds.region,
        "AWS_PAGER": "",
    }


def aws_credentials_ini(creds: AwsCredentials) -> str:
    """Format *creds* as an INI-style AWS credentials file."""
    return (
        "[default]\n"
        f"aws_access_key_id = {creds.access_key_id}\n"
        f"aws_secret_access_key = {creds.secret_access_key}\n"
        f"aws_session_token = {creds.session_token}\n"
        f"region = {creds.region}\n"
    )


def write_aws_credentials_file(creds: AwsCredentials, path: Path) -> None:
    """Write an INI-format AWS credentials file to *path* with mode 0600."""
    content = aws_credentials_ini(creds)
    handle, name = tempfile.mkstemp(prefix="tether-aws-", suffix=".ini")
    tmp = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if path != tmp:
        tmp.replace(path)


def stage_aws_credentials(creds: AwsCredentials) -> StagedFile:
    """Stage the credentials file for a read-write bind mount (caller cleans up).

    The file is world-readable and world-writable *inside* its private staging
    directory so the container process can read it (initial auth) and overwrite
    it (`tether refresh`) whichever uid it runs as.
    """
    return stage(aws_credentials_ini(creds), mode=READ_WRITE_MODE, suffix=".ini")


# ---------------------------------------------------------------------------
# opencode auth
# ---------------------------------------------------------------------------


def opencode_auth_env() -> dict[str, str]:
    """Return ``OPENCODE_AUTH_CONTENT`` from the host opencode auth store.

    opencode stores provider credentials as JSON in
    ``~/.local/share/opencode/auth.json``. The contents are compacted to a
    single line so they can be carried in the env-file, and forwarded alongside
    any provider key configured in the tether profile.
    """
    path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or not data:
        return {}
    return {"OPENCODE_AUTH_CONTENT": json.dumps(data, separators=(",", ":"))}
