from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tether.auth import AuthError, collect_env, env_file, write_env_file
from tether.config import EnvConfig


def test_collect_env_merges_static_and_passthrough() -> None:
    env = EnvConfig(passthrough=["FOO"], static={"BAR": "baz"})
    result = collect_env(env, {"FOO": "bar", "UNUSED": "x"})
    assert result == {"BAR": "baz", "FOO": "bar"}


def test_collect_env_missing_passthrough_raises() -> None:
    with pytest.raises(AuthError, match="NOPE"):
        collect_env(EnvConfig(passthrough=["NOPE"]), {})


def test_write_env_file_permissions_and_content() -> None:
    path = write_env_file({"A": "1", "B": "two words"})
    try:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.read_text(encoding="utf-8") == "A=1\nB=two words\n"
    finally:
        path.unlink(missing_ok=True)


def test_write_env_file_rejects_invalid_name() -> None:
    with pytest.raises(AuthError, match="invalid environment variable name"):
        write_env_file({"bad name": "1"})


def test_write_env_file_rejects_newline_value() -> None:
    with pytest.raises(AuthError, match="unsupported character"):
        write_env_file({"A": "line1\nline2"})


def test_env_file_context_cleans_up() -> None:
    captured: Path | None = None
    with env_file({"A": "1"}) as path:
        captured = path
        assert path is not None
        assert path.exists()
    assert captured is not None
    assert not captured.exists()


def test_env_file_empty_yields_none() -> None:
    with env_file({}) as path:
        assert path is None
