# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim

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
        git \
        jq \
        less \
        procps \
        ripgrep \
        vim-tiny \
 && rm -rf /var/lib/apt/lists/*

RUN npm install --global \
        "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
        "opencode-ai@${OPENCODE_VERSION}" \
        "@google/gemini-cli@${GEMINI_CLI_VERSION}" \
 && npm cache clean --force

# The node image already provides a non-root user named `node` with uid 1000.
RUN mkdir -p /workspace /tmp/tether-home \
 && chown node:node /workspace /tmp/tether-home

COPY entrypoint.sh /usr/local/bin/tether-entrypoint
RUN chmod 0755 /usr/local/bin/tether-entrypoint

WORKDIR /workspace
USER node

ENTRYPOINT ["/usr/local/bin/tether-entrypoint"]
CMD ["bash"]
