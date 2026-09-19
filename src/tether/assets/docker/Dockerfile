# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim

# Fallback pins. `tether build` resolves the latest published versions and
# passes them via --build-arg, so these only apply when resolution fails.
ARG CLAUDE_CODE_VERSION=2.1.270
ARG OPENCODE_VERSION=1.18.30
ARG GEMINI_CLI_VERSION=0.59.0

LABEL org.opencontainers.image.title="tether" \
      org.opencontainers.image.description="AI coding agents confined to a project directory"

ENV DEBIAN_FRONTEND=noninteractive \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
 && rm -rf /var/lib/apt/lists/*

# GitHub CLI apt repository (Debian does not package `gh`).
RUN mkdir -p -m 755 /etc/apt/keyrings \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
        bash-completion \
        gh \
        git \
        jq \
        less \
        ncdu \
        htop \
        procps \
        python3 \
        python3-pip \
        ripgrep \
        sqlite3 \
        tmux \
        tree \
        vim-tiny \
 && ln -sf /usr/bin/pip3 /usr/bin/pip \
 && rm -rf /var/lib/apt/lists/*

# uv: static binary from the official uv image (Debian does not package `uv`).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN npm install --global \
        "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
        "opencode-ai@${OPENCODE_VERSION}" \
        "@google/gemini-cli@${GEMINI_CLI_VERSION}" \
 && npm cache clean --force

# The node image already provides a non-root user named `node` with uid 1000.
RUN mkdir -p /workspace /tmp/tether-home \
 && chown node:node /workspace /tmp/tether-home

COPY --chown=node:node bashrc /tmp/tether-home/.bashrc

COPY entrypoint.sh /usr/local/bin/tether-entrypoint
RUN chmod 0755 /usr/local/bin/tether-entrypoint

WORKDIR /workspace
USER node

ENTRYPOINT ["/usr/local/bin/tether-entrypoint"]
CMD ["bash"]
