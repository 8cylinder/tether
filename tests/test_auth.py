from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from tether.auth import AuthError, collect_env, env_file, opencode_auth_env, write_env_file
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


def _write_opencode_auth(home: Path, content: str) -> None:
    auth_dir = home / ".local" / "share" / "opencode"
    auth_dir.mkdir(parents=True)
    (auth_dir / "auth.json").write_text(content, encoding="utf-8")


def test_opencode_auth_env_compacts_to_single_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_opencode_auth(
        tmp_path, '{\n  "deepseek": {\n    "type": "api",\n    "key": "sk-x"\n  }\n}'
    )
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    env = opencode_auth_env()
    assert set(env) == {"OPENCODE_AUTH_CONTENT"}
    assert "\n" not in env["OPENCODE_AUTH_CONTENT"]
    assert json.loads(env["OPENCODE_AUTH_CONTENT"]) == {"deepseek": {"type": "api", "key": "sk-x"}}


def test_opencode_auth_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert opencode_auth_env() == {}


def test_opencode_auth_env_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_opencode_auth(tmp_path, "not json")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert opencode_auth_env() == {}


def test_opencode_auth_env_empty_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_opencode_auth(tmp_path, "{}")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert opencode_auth_env() == {}
