# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What tether does

Tether runs AI coding agents (Claude Code, opencode, Gemini CLI) inside ephemeral Docker containers confined to a single project directory. The project is mounted read-write but `.git` is mounted read-only on top, so agents can edit files but cannot rewrite history. All capabilities are dropped and resource limits are applied.

## Commands

```bash
uv sync                      # install dependencies
uv run pytest                # run all tests
uv run pytest tests/test_auth.py          # run one test file
uv run pytest tests/test_auth.py::test_collect_env_missing_passthrough_raises  # single test
uv run ruff format .         # format
uv run ruff check .          # lint
uv run ruff check --fix .    # lint with auto-fix
uv run ty check              # type check
```

## Architecture

The CLI (`cli.py`) is a Click group with commands: `init`, `build`, `run`, `shell`, `doctor`, `clean`. The `run` and `shell` commands share a `_launch()` function that orchestrates the full pipeline:

1. **config.py** — Pydantic models loaded from `~/.config/tether/config.toml`. Profiles are keyed by platform name (`linux`, `darwin`) and carry agent choice, env vars, extra mounts, and resource limits. Missing config file returns defaults.

2. **agents.py** — Static registry of `AgentSpec` definitions mapping agent names (`claude`, `opencode`, `gemini`) to their commands and auto-approve flags. `AgentName` is a `Literal` type used for validation throughout.

3. **mounts.py** — Builds the mount policy: project at `/workspace:rw`, `.git` overlay at `/workspace/.git:ro`, plus user-configured extra mounts. The read-only `.git` overlay is the core safety mechanism.

4. **auth.py** — Merges static env vars with host passthrough vars, writes them to a mode-0600 temp file used via `--env-file` (secrets never on the command line), and cleans up on exit.

5. **docker.py** — Builds and runs the `docker run` command with hardening flags (`--cap-drop ALL`, `--security-opt no-new-privileges`, resource limits). Also handles image build/inspect/remove.

6. **platform.py** — Host detection (OS, uid/gid, Docker path, XDG config dir). Profile name defaults to `platform.system().lower()`.

7. **assets/docker/** — Bundled Dockerfile (node:22-bookworm-slim base with all three agent CLIs installed globally via npm) and entrypoint script that handles arbitrary uid mapping.

## Conventions

- Python 3.11+, managed with `uv` and `hatchling` build backend.
- Ruff for linting and formatting (line length 100). Lint rules include type annotations (`ANN`), except `ANN401` is ignored and `ANN201`/`ANN001` are relaxed in tests.
- Type checking with `ty` (target Python 3.11).
- Tests use `pytest` with `tmp_path` fixtures. No Docker required for tests — they exercise the logic layers (config parsing, mount building, command construction, env-file handling) without calling Docker.
- Pydantic models for config, frozen dataclasses with `slots=True` for internal value types (`ContainerMount`, `RunConfig`, `BuildResult`, `HostInfo`, `AgentSpec`).
- `from __future__ import annotations` in every module.
- macOS credential handling (Bedrock/SSO) is explicitly deferred and not yet implemented.
