# Changelog

All notable changes to this project are documented here.

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
