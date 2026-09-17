# tether

Run AI coding agents in a container confined to a project directory.

`tether` launches harnesses such as [Claude Code](https://claude.com/product/claude-code),
[opencode](https://opencode.ai), and the [Gemini CLI](https://github.com/google-gemini/gemini-cli)
inside an ephemeral Docker container. Only the target project is mounted from the
host, with `.git` mounted read-only, so the agent's permission prompts can be
disabled without risking the rest of your filesystem: the worst case is that it
damages the container or the git-backed project.

## Why

Agentic coding tools are most useful when they can run without stopping to ask
for approval on every edit and command. That is only safe if the blast radius is
bounded. `tether` bounds it:

- The host filesystem outside the project is **not visible** inside the jail.
- `.git` is mounted read-only, so history and the object database cannot be
  rewritten or deleted — even by `rm -rf /workspace`.
- Each agent runs with permissive flags: `opencode --auto`, `gemini --yolo`,
  and `claude --permission-mode plan` (plan mode lets Claude run bash freely
  but asks before editing files).

## Requirements

- Linux or macOS
- Docker (Docker Desktop on macOS; Docker Engine on Linux)
- Python 3.11+ and [uv](https://docs.astral.sh/uv/) to install/run the CLI

`tether` targets Docker only. macOS Bedrock credentials are handled via
`aws configure export-credentials`; see [Credentials](#credentials).

## Install

```bash
uv sync          # from a checkout
uv run tether --version
```

To install the `tether` command onto your `PATH`:

```bash
uv tool install .
```

## Quick start

```bash
# 1. Create the config file (~/.config/tether/config.toml)
tether init

# 2. Build the container image for this host
tether build

# 3. Run an agent against the current project
cd ~/projects/my-app
tether run                 # uses the profile's default agent
tether run --agent claude  # or pick one explicitly

# Inspect what would run, without running it
tether run --dry-run
```

## Commands

| Command | Description |
| --- | --- |
| `tether init [--force] [--path P]` | Write the default config file (refuses to overwrite without `--force`). |
| `tether build [--force]` | Build the container image; idempotent unless `--force`. |
| `tether run [options] [-- ARGS...]` | Launch an agent inside the jail. |
| `tether shell [options] [-- ARGS...]` | Open a shell inside the jail (useful for debugging). |
| `tether doctor` | Report host, Docker, config, image, and credential readiness. |
| `tether refresh [CONTAINER]` | Refresh AWS credentials in a running container. |
| `tether clean [-y] [--force]` | Remove the configured image. |

`run`/`shell` options:

- `--agent {claude,opencode,gemini}` — override the profile's agent.
- `-C, --project DIR` — project to confine the agent to (default: cwd).
- `--profile NAME` — config profile to use (default: the platform name).
- `--dry-run` — print the resolved plan and `docker run` command, then exit.
- `--no-build` — fail instead of building a missing image.

Trailing arguments are passed through to the agent, e.g.
`tether run --agent claude -- --resume`.

## Configuration

Default location: `~/.config/tether/config.toml` (honors `XDG_CONFIG_HOME`).

```toml
version = 1
image = "tether:latest"
default_agent = "opencode"

[profiles.linux]
agent = "opencode"

[profiles.linux.env]
passthrough = ["DEEPSEEK_API_KEY"]   # read from the host environment

[profiles.darwin]
agent = "claude"

[profiles.darwin.env]
static = { CLAUDE_CODE_USE_BEDROCK = "1" }

[profiles.darwin.aws_credential_export]
profile = "bedrock"
region = "us-west-2"
```

### Profile fields

| Field | Default | Meaning |
| --- | --- | --- |
| `agent` | `opencode` | Default harness for the profile. |
| `env.passthrough` | `[]` | Host env var names forwarded into the jail. Missing names are an error. |
| `env.static` | `{}` | Literal env vars set inside the jail. |
| `mounts` | `[]` | Extra host paths to expose (see below). |
| `resources.memory` | `4g` | Container memory limit. |
| `resources.cpus` | `2` | CPU limit. |
| `resources.pids_limit` | `1024` | Process limit. |
| `aws_credential_export.profile` | — | AWS CLI profile for credential export (macOS Bedrock). |
| `aws_credential_export.region` | `us-west-2` | AWS region for exported credentials. |

### Extra mounts

```toml
[[profiles.linux.mounts]]
source = "~/shared/reference"
target = "/reference"
mode = "ro"   # or "rw"
```

Sources must exist; `~` is expanded. Prefer `ro`.

## Claude Code settings

When the agent is `claude`, tether mounts the host `~/.claude/` directory and
`~/.claude.json` into the container so that authentication and configuration
carry over. A filtered copy of `settings.json` is mounted read-only on top,
with the following adjustments:

- **Sandbox disabled** (`sandbox.enabled: false`) — the container itself is the
  sandbox, so Claude's internal bash sandbox is redundant.
- **Permissions** — `Bash(*)` is allowed; `Edit` and `Write` are denied, so
  Claude can run any shell command freely but must ask before modifying project
  files directly.
- **Auto-update disabled** (`DISABLE_AUTOUPDATER=1` env var) — the container
  image pins the Claude version, and the npm prefix is not writable.
- **Status line** — a tether indicator is injected.
- **Conflicting keys stripped** — `env`, `awsAuthRefresh`, `permissions`, and
  `sandbox` from the host settings are removed so they don't conflict with
  tether's container configuration.

These settings only apply inside the container. Your host Claude installation is
not affected.

## Safety model

`tether run` executes roughly:

```
docker run --rm --init --workdir /workspace \
  --user "$(id -u):$(id -g)" \
  --volume "$PROJECT:/workspace:rw" \
  --volume "$PROJECT/.git:/workspace/.git:ro" \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 1024 --memory 4g --cpus 2 \
  tether:latest <agent> <auto-approve flags>
```

- **Only the project is mounted.** No `$HOME`, `~/.ssh`, `~/.aws`,
  `~/.config`, Docker socket, or SSH agent.
- **`.git` is read-only.** A nested read-only bind mount cannot be removed or
  written from inside the container, so history survives and can be restored
  with `git checkout`.
- **Hardened.** All capabilities dropped, privilege escalation disabled, and
  resource limits applied.
- **Secrets never touch the command line.** Forwarded environment variables are
  written to a mode-`0600` env-file used via `--env-file` and deleted
  immediately afterward.
- **Full network.** The agent needs the model API, so egress is not restricted.
  `tether` does not protect against data exfiltration.

### Residual risks

- Untracked working-tree files are **not** recoverable if deleted. Commit or
  stash before running an agent on a project with important untracked files.
- A container is not a hard security boundary. With a rootful Docker daemon, a
  container escape could yield host root. `tether` never mounts the Docker
  socket, which removes the easiest escape.
- `.git` mounted read-only means the agent cannot `git commit` inside the jail.
  Commit from the host after reviewing changes.
- Non-git projects are allowed, but a warning is printed because the recovery
  guarantee does not apply.

## Credentials

| Platform | Agent | Mechanism |
| --- | --- | --- |
| Linux | `opencode` | `DEEPSEEK_API_KEY` forwarded from the host environment. |
| macOS | `claude` | AWS credentials exported via `aws configure export-credentials` and injected as env vars. |

On Linux, export the key before launching:

```bash
export DEEPSEEK_API_KEY=sk-...
tether run
```

### macOS / Bedrock

Configure `aws_credential_export` in your profile to use Bedrock via AWS SSO:

```toml
[profiles.darwin]
agent = "claude"

[profiles.darwin.env]
static = { CLAUDE_CODE_USE_BEDROCK = "1" }

[profiles.darwin.aws_credential_export]
profile = "bedrock"
region = "us-west-2"
```

At launch, tether runs `aws configure export-credentials` on the host, parses
the STS tokens, and injects them as environment variables into the container.
If SSO credentials have expired, tether triggers `aws sso login` automatically.

STS tokens are short-lived. To refresh credentials in a running container:

```bash
tether refresh              # auto-detects the running container
tether refresh tether-myapp-abc123  # target a specific container
```

## Development

```bash
uv sync                      # create the environment
uv run pytest                # tests
uv run ruff format .         # format
uv run ruff check .          # lint
uv run ty check              # type check
```

## Related projects (future investigation)

[Docker Sandboxes](https://docs.docker.com/ai/sandboxes/) (`sbx`) is a more
capable superset of this tool and is worth evaluating:

- Runs agents in **microVMs** (a separate kernel), not shared-kernel containers.
- **Deny-by-default networking** through a host proxy, with credentials injected
  host-side so raw API keys never enter the sandbox.
- **Clone mode**: mounts the repository read-only and lets the agent work in a
  private in-VM clone synced back over a git remote — the same protection as our
  read-only `.git`, but it still allows commits.
- Broader agent support (claude, opencode, gemini, codex, copilot, cursor, …).

`tether` is kept intentionally minimal and self-contained: no Docker account
login, no KVM requirement, plain Docker, explicit read-only `.git`, a small
auditable codebase, and ephemeral (`--rm`) containers. Possible ideas to borrow
from `sbx` later: an opt-in clone-based workspace mode and an optional network
egress allowlist.

## Status

Early development. `init`, `build`, `run`, `shell`, `doctor`, `refresh`, and
`clean` work end-to-end on Linux and macOS.
