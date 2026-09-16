# Sandboxed Agent Execution with Nvidia OpenShell



# Sandboxed Agent Execution with NVIDIA OpenShell

Run Claude Code in yolo mode inside an NVIDIA OpenShell sandbox, authenticated to AWS Bedrock for model access and GitHub for repo operations.

## Overview

[OpenShell](https://github.com/NVIDIA/OpenShell) provides sandboxed execution environments for AI agents. Each sandbox runs in an isolated container with policy-enforced network egress, filesystem restrictions (Landlock LSM), and privilege dropping (seccomp). This guide configures a sandbox where Claude Code can:

- Authenticate to **AWS Bedrock** for model inference (via manually injected SSO credentials)
- Access **GitHub** repositories (via provider-injected token)
- Install packages from **PyPI** and **npm**
- Run in "yolo" mode (`--permission-mode dontAsk`) with full bash access

## Architecture Notes

### Why manual AWS credential injection?

OpenShell's provider system replaces real credential values with opaque placeholder tokens (`openshell:resolve:env:*`). The L7 proxy resolves these at egress time. This works for bearer-token auth (e.g., GitHub tokens, API keys) but **breaks AWS SigV4 request signing**, where the SDK uses the secret key to compute an HMAC signature locally. The placeholder string produces an invalid signature, and the proxy never gets a chance to fix it. See [OpenShell #894](https://github.com/NVIDIA/OpenShell/issues/894).

As a workaround, AWS credentials are uploaded directly to the sandbox filesystem and sourced via `.bashrc`. GitHub credentials go through the provider system normally since they use bearer-token auth.

### Network policy

The sandbox starts with no outbound access by default. A custom policy is applied that allows HTTPS traffic to AWS, GitHub, Anthropic (for Claude Code telemetry), and package registries. All traffic passes through OpenShell's HTTP CONNECT proxy. AWS endpoints are configured as **L4 passthrough** (no TLS termination) so SigV4 signatures are not modified in transit.

### Security tradeoffs

- **AWS creds on sandbox filesystem:** By bypassing the provider system, real AWS credentials exist as a file inside the sandbox. The network policy is your primary defense against exfiltration. Keep the egress policy scoped tightly.
- **STS session tokens are time-limited**, which bounds the blast radius. A leaked session token from SSO is typically valid for 1-12 hours depending on your IdP config.
- **No **`protocol: rest`** on AWS endpoints:** If you accidentally set L7 enforcement on Bedrock/STS endpoints, the proxy will MITM the TLS connection and corrupt the SigV4 `Authorization` header.

## Prerequisites

- **Docker** - Docker Desktop (or a Docker daemon) must be running
- **AWS CLI v2** - installed locally with an SSO profile configured
- **GitHub CLI** (`gh`) - authenticated locally (`gh auth login`)
- **macOS or Linux** host machine

## Configuration

Before running the scripts, edit the following variables at the top of `create-sandbox.sh` and `refresh-aws-creds.sh`:

| Variable | Description |
| --- | --- |
| `AWS_PROFILE` | Your AWS SSO profile name |
| `AWS_REGION` | AWS region for Bedrock (e.g., `us-west-2`) |

The Claude Code settings file includes Bedrock model identifiers. Update these in `first-time-setup.sh` if your account has access to different model versions.

## Setup Scripts

Three scripts handle the full lifecycle. Save them to a directory (e.g., `~/openshell-setup/`) and run `chmod +x *.sh`.

### 1. first-time-setup.sh

Run **once** on a new machine. Installs the OpenShell CLI, starts a local gateway, creates credential providers, and writes the network policy and Claude Code settings files that the other scripts reference.

```none
#!/bin/bash
# first-time-setup.sh
#
# One-time setup: install OpenShell CLI, start gateway, create providers,
# and write config files used by create-sandbox.sh and refresh-aws-creds.sh.
#
# Usage: ./first-time-setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing OpenShell CLI..."
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh

echo ""
echo "==> Starting local gateway..."
openshell gateway start || echo "    Gateway already running (this is fine)"

echo ""
echo "==> Creating GitHub provider..."
GITHUB_TOKEN=$(gh auth token 2>/dev/null || true)
if [ -z "$GITHUB_TOKEN" ]; then
    echo "    ERROR: gh CLI not authenticated. Run 'gh auth login' first."
    exit 1
fi
export GITHUB_TOKEN
openshell provider delete github
openshell provider create \
    --name github \
    --type generic \
    --credential GITHUB_TOKEN
echo "    GitHub provider ready."

echo ""
echo "==> Writing network policy file..."
cat > "$SCRIPT_DIR/openshell-outbound-policy.yaml" << 'POLICY'
version: 1

filesystem_policy:
  include_workdir: true
  read_only:
    - /usr
    - /lib
    - /proc
    - /dev/urandom
    - /app
    - /etc
    - /var/log
  read_write:
    - /sandbox
    - /tmp
    - /dev/null

landlock:
  compatibility: best_effort

process:
  run_as_user: sandbox
  run_as_group: sandbox

network_policies:
  aws:
    name: aws
    endpoints:
      - { host: "*.amazonaws.com", port: 443 }
      - { host: "*.*.amazonaws.com", port: 443 }
      - { host: "*.*.*.amazonaws.com", port: 443 }
    binaries:
      - { path: "/**" }

  github:
    name: github
    endpoints:
      - { host: "github.com", port: 443 }
      - { host: "*.github.com", port: 443 }
      - { host: "*.githubusercontent.com", port: 443 }
    binaries:
      - { path: "/**" }

  claude_code:
    name: claude-code
    endpoints:
      - { host: "sentry.io", port: 443 }
      - { host: "*.claude.com", port: 443 }
      - { host: "*.anthropic.com", port: 443 }
    binaries:
      - { path: "/**" }

  package_managers:
    name: package-managers
    endpoints:
      - { host: "pypi.org", port: 443 }
      - { host: "*.pythonhosted.org", port: 443 }
      - { host: "*.npmjs.org", port: 443 }
      - { host: "*.python.org", port: 443 }
    binaries:
      - { path: "/**" }
POLICY
echo "    Written to: $SCRIPT_DIR/openshell-outbound-policy.yaml"

echo ""
echo "==> Writing Claude Code settings file..."
cat > "$SCRIPT_DIR/claude-settings.json" << 'SETTINGS'
{
  "env": {
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "global.anthropic.claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "global.anthropic.claude-opus-4-6-v1"
  },
  "model": "opusplan",
  "alwaysThinkingEnabled": false,
  "permissions": {
    "allow": [
      "Read",
      "Write",
      "Edit",
      "Bash(*)"
    ],
    "deny": []
  }
}
SETTINGS
echo "    Written to: $SCRIPT_DIR/claude-settings.json"

echo ""
echo "==> First-time setup complete."
echo ""
echo "Next steps:"
echo "  1. Edit AWS_PROFILE and AWS_REGION in create-sandbox.sh and refresh-aws-creds.sh"
echo "  2. Run: ./create-sandbox.sh <sandbox-name>"
```

### 2. create-sandbox.sh \<name\>

Creates a new sandbox, configures it, installs AWS CLI v2, uploads Claude Code settings, injects AWS credentials, and runs validation tests. Calls `refresh-aws-creds.sh` internally.

```
#!/bin/bash
# create-sandbox.sh
#
# Create and configure an OpenShell sandbox for Claude Code with AWS Bedrock.
# Installs AWS CLI v2, uploads Claude Code settings, injects AWS credentials,
# and runs validation tests.
#
# Usage: ./create-sandbox.sh <sandbox-name>
#
# Prerequisites:
#   - first-time-setup.sh has been run
#   - Docker is running
#   - AWS SSO profile is configured

set -euo pipefail

# ─── Configuration ──────────────────────────────────────────────────
AWS_PROFILE="your-bedrock-profile"    # <-- EDIT THIS
AWS_REGION="us-west-2"                # <-- EDIT THIS
# ────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POLICY_FILE="$SCRIPT_DIR/openshell-outbound-policy.yaml"
SETTINGS_FILE="$SCRIPT_DIR/claude-settings.json"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <sandbox-name>"
    exit 1
fi

SANDBOX_NAME="$1"

# Validate prerequisites
if [ ! -f "$POLICY_FILE" ]; then
    echo "ERROR: $POLICY_FILE not found. Run first-time-setup.sh first."
    exit 1
fi
if [ ! -f "$SETTINGS_FILE" ]; then
    echo "ERROR: $SETTINGS_FILE not found. Run first-time-setup.sh first."
    exit 1
fi

echo "==> Creating sandbox: $SANDBOX_NAME"
openshell sandbox create \
    --name "$SANDBOX_NAME" \
    --provider github \
    -- bash -c "echo 'Sandbox created.'"

echo ""
echo "==> Applying network policy..."
openshell policy set "$SANDBOX_NAME" --policy "$POLICY_FILE" --wait

echo ""
echo "==> Configuring sandbox shell..."
openshell sandbox exec -n "$SANDBOX_NAME" -- \
    bash -c 'echo "source /sandbox/.aws-creds.sh 2>/dev/null" >> /sandbox/.bashrc'
openshell sandbox exec -n "$SANDBOX_NAME" -- \
    bash -c 'echo "alias claude=\"claude --permission-mode dontAsk\"" >> /sandbox/.bashrc'

echo ""
echo "==> Installing AWS CLI v2 (this may take a few minutes)..."
openshell sandbox exec -n "$SANDBOX_NAME" -- \
    bash -c 'GIT_SSL_NO_VERIFY=1 pip install -q git+https://github.com/aws/aws-cli.git@v2'

echo ""
echo "==> Uploading Claude Code settings..."
openshell sandbox upload "$SANDBOX_NAME" "$SETTINGS_FILE" /sandbox/.claude/settings.json

echo ""
echo "==> Injecting AWS credentials..."
"$SCRIPT_DIR/refresh-aws-creds.sh" "$SANDBOX_NAME"

echo ""
echo "==> Testing Claude Code with Bedrock..."
openshell sandbox exec -n "$SANDBOX_NAME" -- \
    bash -lc 'claude -p "write the word test to file /sandbox/test.file"'

TEST_RESULT=$(openshell sandbox exec -n "$SANDBOX_NAME" -- bash -lc 'cat /sandbox/test.file 2>/dev/null || echo "MISSING"')
if echo "$TEST_RESULT" | grep -qi "test"; then
    echo "    Claude Code test PASSED."
else
    echo "    WARNING: Claude Code test may have failed. Check manually:"
    echo "    openshell sandbox connect $SANDBOX_NAME"
fi

echo ""
echo "==> Sandbox '$SANDBOX_NAME' is ready."
echo ""
echo "Connect with:"
echo "  openshell sandbox connect $SANDBOX_NAME"
echo ""
echo "Refresh AWS creds when SSO expires:"
echo "  ./refresh-aws-creds.sh $SANDBOX_NAME"
```

### 3. refresh-aws-creds.sh \<sandbox-name\>

Re-authenticates via AWS SSO, exports fresh temporary credentials, and uploads them to an existing sandbox. Run this when your SSO session expires.

```
#!/bin/bash
# refresh-aws-creds.sh
#
# Re-authenticate via AWS SSO, export fresh temporary credentials,
# and upload them to an existing OpenShell sandbox.
#
# Usage: ./refresh-aws-creds.sh <sandbox-name>

set -euo pipefail

# ─── Configuration ──────────────────────────────────────────────────
AWS_PROFILE="your-bedrock-profile"    # <-- EDIT THIS
AWS_REGION="us-west-2"                # <-- EDIT THIS
# ────────────────────────────────────────────────────────────────────

if [ $# -ne 1 ]; then
    echo "Usage: $0 <sandbox-name>"
    exit 1
fi

SANDBOX_NAME="$1"
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT

echo "==> Authenticating via AWS SSO (profile: $AWS_PROFILE)..."
aws sso login --profile "$AWS_PROFILE"

echo ""
echo "==> Exporting temporary credentials..."
eval $(aws configure export-credentials --profile "$AWS_PROFILE" --format env)

if [ -z "${AWS_ACCESS_KEY_ID:-}" ]; then
    echo "ERROR: Failed to export credentials. Check your AWS profile."
    exit 1
fi

echo ""
echo "==> Uploading credentials to sandbox: $SANDBOX_NAME"
cat > "$TMPFILE" << EOF
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
export AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN
export AWS_REGION=$AWS_REGION
export AWS_DEFAULT_REGION=$AWS_REGION
export AWS_PAGER=
EOF

openshell sandbox upload "$SANDBOX_NAME" "$TMPFILE" /sandbox/.aws-creds.sh

echo ""
echo "==> Validating AWS credentials in sandbox..."
STS_OUTPUT=$(openshell sandbox exec -n "$SANDBOX_NAME" -- \
    bash -lc 'aws sts get-caller-identity 2>&1') || true

if echo "$STS_OUTPUT" | grep -q "Account"; then
    echo "    AWS credentials valid."
    echo "    $STS_OUTPUT"
else
    echo "    WARNING: AWS credential check returned unexpected output:"
    echo "    $STS_OUTPUT"
    echo ""
    echo "    Try connecting manually to debug:"
    echo "    openshell sandbox connect $SANDBOX_NAME"
fi

echo ""
echo "==> Credentials refreshed for sandbox '$SANDBOX_NAME'."
echo "    NOTE: If Claude Code is currently running, restart it to pick up new creds."
```

## Usage

After setup, connect to a sandbox and start working:

```
openshell sandbox connect my-project
cd /sandbox
git clone https://github.com/your-org/your-repo.git
cd your-repo
claude
```

Or for a one-shot Claude Code command:

```
openshell sandbox exec -n my-project -- bash -lc \
'cd /sandbox/your-repo && claude -p "explain this codebase"'
```

## Sandbox Lifecycle Commands

| **Action** | **Command** |
| --- | --- |
| List sandboxes | `openshell sandbox list` |
| Connect | `openshell sandbox connect <name>` |
| Run a command | `openshell sandbox exec -n <name> -- bash -lc '<command>'` |
| View logs | `openshell logs <name> --tail` |
| Check policy denials | `openshell logs <name> --tail --source sandbox` |
| Upload files | `openshell sandbox upload <name> ./local /sandbox/remote` |
| Download files | `openshell sandbox download <name> /sandbox/remote ./local` |
| Delete | `openshell sandbox delete <name>` |
| Refresh AWS creds | `./refresh-aws-creds.sh <name>` |

## Working with Repositories

OpenShell does not support bind-mounting host directories into the sandbox. Your options for getting code in and out:

| Method | Description |
| --- | --- |
| **Git clone inside sandbox** (recommended) | Clone from GitHub inside the sandbox. Push/pull as normal. Best alignment with the isolation model. |
| **Mutagen sync** | Bidirectional file sync over SSH. Install with `brew install mutagen-io/mutagen/mutagen`. Closest experience to a bind mount. |
| **VS Code / Cursor Remote** | `openshell sandbox create --editor vscode` opens a remote SSH editing session. |
| **Upload / Download** | `openshell sandbox upload` and `download` for one-off file transfers. Not bidirectional. |

## Troubleshooting

| Error | Cause | Fix |
| --- | --- | --- |
| `CONNECT tunnel failed, response 403` | Network policy blocking outbound to a host | Check `openshell logs <name> --tail --source sandbox` for the denied hostname and add it to the policy YAML |
| `SignatureDoesNotMatch` / `InvalidSignature` | AWS creds went through provider placeholder mangling | Re-run `refresh-aws-creds.sh` to upload real credentials |
| `server certificate verification failed` | OpenShell proxy TLS termination | Prefix git commands with `GIT_SSL_NO_VERIFY=1` |
| `SSO token has expired` | AWS session expired | Run `./refresh-aws-creds.sh <name>` |
| `aws: command not found` | Sandbox was recreated; AWS CLI v2 doesn't persist | Re-run `create-sandbox.sh` |
| `Unable to redirect output to pager` | `less` not installed in sandbox | Set `export AWS_PAGER=""` (already handled by the creds script) |
