# Changelog

All notable changes to this project are documented here.

## Unreleased

- Add a `[docker]` configuration section with `extra_args`, which passes
  additional flags to `docker run` for every harness. This lets `tether run`
  and `tether shell` reach services on the host, such as a host-run Ollama
  server via `--add-host=host.docker.internal:host-gateway`.
- Add `tether local ollama`, which checks a host Ollama server and prints the
  commands needed to expose it to the container.

## 0.3.0

- Run OpenCode, Claude Code, or Google Antigravity in a disposable Docker
  container.
- Mount harness configuration, symlinked config files, and the project
  directory into the container.
- Build and clean the container image with `tether build` and `tether clean`.
- Inspect configuration, mounts, and Docker status with `tether info`.
- Generate static bash completions with `tether --completions`.
- Print the platform config path with `tether --config`.
- Control color with `--color`, `NO_COLOR`, `FORCE_COLOR`, and `TERM=dumb`.
