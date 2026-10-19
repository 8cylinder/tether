FROM node:22-bookworm-slim

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG UID=1000
ARG GID=1000

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        curl \
        fd-find \
        git \
        gnupg \
        jq \
        less \
        libsecret-1-0 \
        make \
        nano \
        openssh-client \
        pipx \
        procps \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
        sudo \
        tmux \
        unzip \
        vim \
        wget \
        zip \
        zsh \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && rm -rf /var/lib/apt/lists/*

# AI harnesses installed globally for every user in the image.
RUN npm install --global \
        @opencode/cli@latest \
        @anthropic-ai/claude-code@latest \
    && npm cache clean --force

# Non-root user mirroring the host UID/GID so files stay owned by you.
RUN userdel -r node 2>/dev/null || true; \
    groupdel node 2>/dev/null || true; \
    groupadd --gid "${GID}" tether; \
    useradd --create-home --uid "${UID}" --gid "${GID}" --shell /bin/bash tether

USER tether
ENV HOME=/home/tether
ENV PATH=/home/tether/.local/bin:${PATH}

# Google Antigravity CLI (installs agy into ~/.local/bin).
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash

WORKDIR /workdir
CMD ["bash"]
