"""Configuration model and TOML loading for tether."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from tether.agents import AgentName
from tether.platform import config_dir

MountMode = Literal["ro", "rw"]

CONFIG_FILENAME = "config.toml"


class Mount(BaseModel):
    """A host path exposed to the jail."""

    source: str
    target: str
    mode: MountMode = "ro"


class EnvConfig(BaseModel):
    """Environment variables forwarded into the jail."""

    passthrough: list[str] = Field(default_factory=list)
    static: dict[str, str] = Field(default_factory=dict)


class Resources(BaseModel):
    """Container resource limits."""

    memory: str = "4g"
    cpus: str = "2"
    pids_limit: int = 1024


class Profile(BaseModel):
    """Per-platform runtime settings."""

    agent: AgentName = "opencode"
    env: EnvConfig = Field(default_factory=EnvConfig)
    mounts: list[Mount] = Field(default_factory=list)
    resources: Resources = Field(default_factory=Resources)


class Config(BaseModel):
    """Top-level tether configuration."""

    version: int = 1
    image: str = "tether:latest"
    default_agent: AgentName = "opencode"
    profiles: dict[str, Profile] = Field(default_factory=dict)

    def profile_for(self, name: str) -> Profile:
        """Return the profile for *name*, falling back to the default agent."""
        return self.profiles.get(name, Profile(agent=self.default_agent))


def default_config_path() -> Path:
    """Return the default path to the tether config file."""
    return config_dir() / CONFIG_FILENAME


def load_config(path: Path | None = None) -> Config:
    """Load configuration from *path*, or return defaults when it is missing."""
    target = path or default_config_path()
    if not target.exists():
        return Config()
    with target.open("rb") as handle:
        data = tomllib.load(handle)
    return Config.model_validate(data)


DEFAULT_CONFIG_TOML = """\
# tether configuration
version = 1
image = "tether:latest"
default_agent = "opencode"

[profiles.linux]
agent = "opencode"

[profiles.linux.env]
passthrough = ["DEEPSEEK_API_KEY"]

[profiles.darwin]
agent = "claude"
# macOS Bedrock/SSO authentication is not finalized yet; see design notes.

[profiles.darwin.env]
static = { CLAUDE_CODE_USE_BEDROCK = "1", AWS_PROFILE = "bedrock" }
"""


def write_default_config(path: Path | None = None, *, force: bool = False) -> Path:
    """Write the default config file.

    Raises:
        FileExistsError: when the target exists and *force* is false.
    """
    target = path or default_config_path()
    if target.exists() and not force:
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return target
