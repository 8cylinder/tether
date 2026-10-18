"""Registry of supported AI harnesses."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Harness:
    """A supported agent CLI and the host config it needs mounted."""

    name: str
    command: tuple[str, ...]
    description: str
    default_mounts: tuple[str, ...]
    default_args: tuple[str, ...] = ()


HARNESSES: dict[str, Harness] = {
    "opencode": Harness(
        name="opencode",
        command=("opencode",),
        description="OpenCode",
        default_args=("--auto",),
        default_mounts=(
            "~/.config/opencode",
            "~/.local/share/opencode",
            "~/.local/state/opencode",
            "~/.cache/opencode",
        ),
    ),
    "claude": Harness(
        name="claude",
        command=("claude",),
        description="Anthropic Claude Code",
        default_mounts=(
            "~/.claude",
            "~/.claude.json",
            "~/.config/claude",
        ),
    ),
    "antigravity": Harness(
        name="antigravity",
        command=("agy",),
        description="Google Antigravity",
        default_mounts=(
            "~/.gemini/antigravity-cli",
            "~/.antigravity",
        ),
    ),
}

AGENT_CHOICES: tuple[str, ...] = tuple(HARNESSES)

DEFAULT_AGENT = "opencode"
