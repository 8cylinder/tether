# tether

Run AI coding harnesses inside a disposable Docker container with full
permissions, so an agent can do anything it wants inside `/workdir` without
being able to damage your host outside the mounted project directory.

Supported harnesses:

| name          | command             | description            |
| ------------- | ------------------- | ---------------------- |
| `opencode`    | `opencode --auto`   | OpenCode               |
| `claude`      | `claude`            | Anthropic Claude Code  |
| `antigravity` | `agy`               | Google Antigravity     |

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
tether build                              # build/rebuild the container image
tether build --update-software            # rebuild and upgrade all installed software
tether build --install-completion         # print a command to enable tab completion
tether build --install-global-completion  # print a system-wide completion command
tether run                                # run the default harness
tether run --agent=opencode               # run a specific harness
tether shell                              # interactive shell at /workdir
tether info                               # configuration and status
tether clean                              # remove the built image
```

`tether run` and `tether shell` mount the current directory at `/workdir` in a
fresh, disposable container (`docker run --rm`).

`tether build --install-completion` detects the shell from `$SHELL` and prints a
command that appends completion setup to the appropriate startup file
(`~/.bashrc`, `~/.zshrc`, or `~/.config/fish/config.fish`).
`tether build --install-global-completion` prints commands that install
completion for all users (the install command requires `sudo`) and load it in
the current shell. No files are modified until you run the printed commands.

## Configuration

tether reads `~/.config/tether/config.toml` (created automatically on first
run). `default` selects the harness used by `tether run` when `--agent` is
omitted. Each harness section lists the host paths that are bind-mounted into
the container so that settings, prompts and history carry over between
sessions, and the `args` passed to the harness when it starts.

```toml
default = "opencode"

[opencode]
args = ["--auto"]
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

- `args` overrides the arguments passed to the harness; omit it to use the
  harness defaults (for example `--auto` for `opencode`). Set it to an empty
  list to pass none.
- `~` and environment variables are expanded.
- Host paths under `$HOME` are mounted to the same path under the container
  user's home (`/home/tether`), so the harnesses find their settings.
- Missing directories are created on first run; missing files are skipped with a
  warning (a file such as `~/.claude.json` will appear once the host tool
  creates it).
- Symlinks at the top level of a mounted directory that point outside it (for
  example an `opencode.jsonc` linked to `~/dotfiles/opencode.jsonc`) are mounted
  too, at the path they resolve to inside the container, so they still resolve.
  Broken links are reported and skipped.

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
  settings are taken from the host. Run `tether build --update-software` to
  bypass the build cache and pull the latest base image and tool versions.
- The image is built with your host UID/GID so files created in `/workdir` stay
  owned by you.
- OAuth sign-in may not work inside a container without a browser. Prefer
  authenticating on the host and mounting the result, or use API keys via
  environment variables.
