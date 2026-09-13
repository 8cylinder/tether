# tether

Run AI coding agents in a container confined to a project directory.

tether launches harnesses such as Claude Code, opencode, and the Gemini CLI inside
an ephemeral Docker container. Only the target project is mounted from the host,
with `.git` mounted read-only, so the agent's permission prompts can be disabled
without risking the rest of your filesystem.

See the design notes for the full architecture and the deferred macOS
authentication work.

## Status

Early development. The CLI, configuration, and container integration are being
built in milestones.
