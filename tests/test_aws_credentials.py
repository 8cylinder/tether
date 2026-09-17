from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from tether.auth import (
    AuthError,
    AwsCredentials,
    _parse_export_env,
    aws_credential_env,
    export_aws_credentials,
    find_aws_cli,
    resolve_aws_credentials,
    run_sso_login,
    write_aws_credentials_file,
)
from tether.config import AwsCredentialExport

VALID_EXPORT_OUTPUT = """\
export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
export AWS_SESSION_TOKEN=FwoGZXIvYXdzEBY+token
export AWS_CREDENTIAL_EXPIRATION=2026-09-16T18:00:00Z
"""


# -- _parse_export_env -------------------------------------------------------


def test_parse_export_env_valid() -> None:
    result = _parse_export_env(VALID_EXPORT_OUTPUT)
    assert result["AWS_ACCESS_KEY_ID"] == "AKIAIOSFODNN7EXAMPLE"
    assert result["AWS_SECRET_ACCESS_KEY"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    assert result["AWS_SESSION_TOKEN"] == "FwoGZXIvYXdzEBY+token"
    assert result["AWS_CREDENTIAL_EXPIRATION"] == "2026-09-16T18:00:00Z"


def test_parse_export_env_blank_lines_and_comments() -> None:
    output = "\n# comment\nexport FOO=bar\n\n"
    result = _parse_export_env(output)
    assert result == {"FOO": "bar"}


def test_parse_export_env_value_with_equals() -> None:
    output = "export TOKEN=abc=def=ghi\n"
    result = _parse_export_env(output)
    assert result["TOKEN"] == "abc=def=ghi"


def test_parse_export_env_bare_key_value() -> None:
    output = "KEY=value\n"
    result = _parse_export_env(output)
    assert result["KEY"] == "value"


def test_parse_export_env_empty() -> None:
    assert _parse_export_env("") == {}
    assert _parse_export_env("\n\n") == {}


# -- find_aws_cli ------------------------------------------------------------


def test_find_aws_cli_found() -> None:
    with patch("tether.auth.shutil.which", return_value="/usr/local/bin/aws"):
        assert find_aws_cli() == "/usr/local/bin/aws"


def test_find_aws_cli_missing() -> None:
    with (
        patch("tether.auth.shutil.which", return_value=None),
        pytest.raises(AuthError, match="not found on PATH"),
    ):
        find_aws_cli()


# -- export_aws_credentials --------------------------------------------------


def test_export_aws_credentials_happy_path() -> None:
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=VALID_EXPORT_OUTPUT)
    with (
        patch("tether.auth.find_aws_cli", return_value="/usr/local/bin/aws"),
        patch("tether.auth.subprocess.run", return_value=completed),
    ):
        creds = export_aws_credentials("bedrock", "us-west-2")
    assert creds.access_key_id == "AKIAIOSFODNN7EXAMPLE"
    assert creds.secret_access_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    assert creds.session_token == "FwoGZXIvYXdzEBY+token"
    assert creds.region == "us-west-2"
    assert creds.expiration == datetime(2026, 9, 16, 18, 0, 0, tzinfo=UTC)


def test_export_aws_credentials_no_expiration() -> None:
    output = (
        "export AWS_ACCESS_KEY_ID=AKIA\n"
        "export AWS_SECRET_ACCESS_KEY=secret\n"
        "export AWS_SESSION_TOKEN=tok\n"
    )
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=output)
    with (
        patch("tether.auth.find_aws_cli", return_value="/usr/local/bin/aws"),
        patch("tether.auth.subprocess.run", return_value=completed),
    ):
        creds = export_aws_credentials("bedrock", "eu-west-1")
    assert creds.expiration is None
    assert creds.region == "eu-west-1"


def test_export_aws_credentials_subprocess_failure() -> None:
    with (
        patch("tether.auth.find_aws_cli", return_value="/usr/local/bin/aws"),
        patch(
            "tether.auth.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "aws", stderr="SSO token expired"),
        ),
        pytest.raises(AuthError, match="SSO token expired"),
    ):
        export_aws_credentials("bedrock", "us-west-2")


def test_export_aws_credentials_missing_key() -> None:
    output = "export AWS_ACCESS_KEY_ID=AKIA\nexport AWS_SECRET_ACCESS_KEY=secret\n"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=output)
    with (
        patch("tether.auth.find_aws_cli", return_value="/usr/local/bin/aws"),
        patch("tether.auth.subprocess.run", return_value=completed),
        pytest.raises(AuthError, match="AWS_SESSION_TOKEN"),
    ):
        export_aws_credentials("bedrock", "us-west-2")


def test_export_aws_credentials_timeout() -> None:
    with (
        patch("tether.auth.find_aws_cli", return_value="/usr/local/bin/aws"),
        patch(
            "tether.auth.subprocess.run",
            side_effect=subprocess.TimeoutExpired("aws", 30),
        ),
        pytest.raises(AuthError, match="timed out"),
    ):
        export_aws_credentials("bedrock", "us-west-2")


# -- run_sso_login -----------------------------------------------------------


def test_run_sso_login_success() -> None:
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    with (
        patch("tether.auth.find_aws_cli", return_value="/usr/local/bin/aws"),
        patch("tether.auth.subprocess.run", return_value=completed),
    ):
        run_sso_login("bedrock")


def test_run_sso_login_failure() -> None:
    completed = subprocess.CompletedProcess(args=[], returncode=1)
    with (
        patch("tether.auth.find_aws_cli", return_value="/usr/local/bin/aws"),
        patch("tether.auth.subprocess.run", return_value=completed),
        pytest.raises(AuthError, match="sso login failed"),
    ):
        run_sso_login("bedrock")


# -- resolve_aws_credentials -------------------------------------------------


def test_resolve_succeeds_first_try() -> None:
    creds = AwsCredentials(
        access_key_id="AKIA",
        secret_access_key="secret",
        session_token="tok",
        region="us-west-2",
    )
    config = AwsCredentialExport(profile="bedrock")
    with patch("tether.auth.export_aws_credentials", return_value=creds) as mock_export:
        result = resolve_aws_credentials(config)
    assert result is creds
    mock_export.assert_called_once_with("bedrock", "us-west-2")


def test_resolve_retries_after_sso_login() -> None:
    creds = AwsCredentials(
        access_key_id="AKIA",
        secret_access_key="secret",
        session_token="tok",
        region="us-west-2",
    )
    config = AwsCredentialExport(profile="bedrock")
    with (
        patch(
            "tether.auth.export_aws_credentials",
            side_effect=[AuthError("expired"), creds],
        ) as mock_export,
        patch("tether.auth.run_sso_login") as mock_login,
    ):
        result = resolve_aws_credentials(config)
    assert result is creds
    assert mock_export.call_count == 2
    mock_login.assert_called_once_with("bedrock")


def test_resolve_fails_after_sso_login_fails() -> None:
    config = AwsCredentialExport(profile="bedrock")
    with (
        patch("tether.auth.export_aws_credentials", side_effect=AuthError("expired")),
        patch("tether.auth.run_sso_login", side_effect=AuthError("login failed")),
        pytest.raises(AuthError, match="login failed"),
    ):
        resolve_aws_credentials(config)


def test_resolve_fails_after_sso_login_succeeds_but_export_still_fails() -> None:
    config = AwsCredentialExport(profile="bedrock")
    with (
        patch("tether.auth.export_aws_credentials", side_effect=AuthError("still broken")),
        patch("tether.auth.run_sso_login"),
        pytest.raises(AuthError, match="still broken"),
    ):
        resolve_aws_credentials(config)


# -- aws_credential_env ------------------------------------------------------


def test_aws_credential_env() -> None:
    creds = AwsCredentials(
        access_key_id="AKIA",
        secret_access_key="secret",
        session_token="tok",
        region="us-west-2",
    )
    env = aws_credential_env(creds)
    assert "AWS_ACCESS_KEY_ID" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "AWS_SESSION_TOKEN" not in env
    assert env["AWS_REGION"] == "us-west-2"
    assert env["AWS_DEFAULT_REGION"] == "us-west-2"
    assert env["AWS_PAGER"] == ""


# -- write_aws_credentials_file ----------------------------------------------


def test_write_aws_credentials_file(tmp_path: Path) -> None:
    creds = AwsCredentials(
        access_key_id="AKIA",
        secret_access_key="secret",
        session_token="tok",
        region="us-west-2",
    )
    target = tmp_path / "credentials"
    write_aws_credentials_file(creds, target)
    content = target.read_text(encoding="utf-8")
    assert "[default]" in content
    assert "aws_access_key_id = AKIA" in content
    assert "aws_secret_access_key = secret" in content
    assert "aws_session_token = tok" in content
    assert "region = us-west-2" in content
