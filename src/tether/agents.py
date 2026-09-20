"""Definitions for the AI coding harnesses tether can run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AgentName = Literal["claude", "opencode", "gemini"]


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """How to launch a harness inside the jail."""

    name: AgentName
    command: tuple[str, ...]
    description: str = ""
    resume_flag: str | None = None


AGENTS: dict[str, AgentSpec] = {
    "claude": AgentSpec(
        name="claude",
        command=("claude", "--permission-mode", "plan"),
        description="Anthropic Claude Code",
    ),
    "opencode": AgentSpec(
        name="opencode",
        command=("opencode",),
        description="opencode",
        resume_flag="--continue",
    ),
    "gemini": AgentSpec(
        name="gemini",
        command=("gemini", "--yolo"),
        description="Google Gemini CLI",
    ),
}


def get_agent(name: str) -> AgentSpec:
    """Return the agent spec for *name*.

    Raises:
        KeyError: when *name* is not a known agent.
    """
    return AGENTS[name]
