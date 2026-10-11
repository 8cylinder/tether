# tether

Run AI coding harnesses inside a disposable Docker container with full
permissions, so an agent can do anything it wants inside `/workdir` without
being able to damage your host outside the mounted project directory.

Supported harnesses:

| name          | command    | description            |
| ------------- | ---------- | ---------------------- |
| `opencode`    | `opencode` | OpenCode               |
| `claude`      | `claude`   | Anthropic Claude Code  |
| `antigravity` | `agy`      | Google Antigravity     |

## Requirements

- Docker Engine (or Docker Desktop) with a running daemon
- [`uv`](https://docs.astral.sh/uv/) for development

## Install

```bash
make install        # uv sync
uv run tether --help
```

## Usage

```bash
tether build                    # build/rebuild the container image
tether run                      # run the default harness
tether run --agent=opencode     # run a specific harness
tether shell                    # interactive shell at /workdir
tether info                     # configuration and status
tether clean                    # remove the built image
```

`tether run` and `tether shell` mount the current directory at `/workdir` in a
fresh, disposable container (`docker run --rm`).

## Configuration

tether reads `~/.config/tether/config.toml` (created automatically on first
run). `default` selects the harness used by `tether run` when `--agent` is
omitted. Each harness section lists the host paths that are bind-mounted into
the container so that settings, prompts and history carry over between
sessions.

```toml
default = "opencode"

[opencode]
mount = [
    "~/.config/opencode",
    "~/.local/share/opencode",
    "~/.local/state/opencode",
    "~/.cache/opencode",
]

[claude]
mount = [
    "~/.claude",
    "~/.claude.json",
    "~/.config/claude",
]

[antigravity]
mount = [
    "~/.gemini/antigravity-cli",
    "~/.antigravity",
]
```

- `~` and environment variables are expanded.
- Host paths under `$HOME` are mounted to the same path under the container
  user's home (`/home/tether`), so the harnesses find their settings.
- Missing directories are created on first run; missing files are skipped with a
  warning (a file such as `~/.claude.json` will appear once the host tool
  creates it).

## Development

```bash
make lint          # ruff check
make format        # ruff format
make typecheck     # ty check
make test          # pytest
make check         # all of the above
```

## Notes

- The harnesses are installed inside the image at build time; only their
  settings are taken from the host.
- The image is built with your host UID/GID so files created in `/workdir` stay
  owned by you.
- OAuth sign-in may not work inside a container without a browser. Prefer
  authenticating on the host and mounting the result, or use API keys via
  environment variables.
