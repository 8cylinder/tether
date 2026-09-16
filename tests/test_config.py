from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tether.config import AwsCredentialExport, Config, load_config, write_default_config


def test_defaults_when_missing(tmp_path: Path) -> None:
    config = load_config(tmp_path / "missing.toml")
    assert config.version == 1
    assert config.default_agent == "opencode"
    assert config.profiles == {}


def test_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_default_config(path)
    config = load_config(path)
    assert config.profiles["linux"].agent == "opencode"
    assert config.profiles["linux"].env.passthrough == ["DEEPSEEK_API_KEY"]
    assert config.profiles["darwin"].env.static["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert "AWS_PROFILE" not in config.profiles["darwin"].env.static
    export = config.profiles["darwin"].aws_credential_export
    assert export is not None
    assert export.profile == "bedrock"
    assert export.region == "us-west-2"


def test_write_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_default_config(path)
    with pytest.raises(FileExistsError):
        write_default_config(path)


def test_write_force_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("version = 99\n", encoding="utf-8")
    write_default_config(path, force=True)
    assert load_config(path).version == 1


def test_profile_for_falls_back_to_default_agent() -> None:
    config = Config(default_agent="gemini")
    assert config.profile_for("unknown").agent == "gemini"


def test_invalid_agent_rejected() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({"profiles": {"linux": {"agent": "bogus"}}})


def test_aws_credential_export_defaults_to_none() -> None:
    config = Config()
    profile = config.profile_for("anything")
    assert profile.aws_credential_export is None


def test_aws_credential_export_region_default() -> None:
    export = AwsCredentialExport(profile="my-profile")
    assert export.region == "us-west-2"


def test_aws_credential_export_custom_region() -> None:
    export = AwsCredentialExport(profile="my-profile", region="eu-west-1")
    assert export.region == "eu-west-1"
