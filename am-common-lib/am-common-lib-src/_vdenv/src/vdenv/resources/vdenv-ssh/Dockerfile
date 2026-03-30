# vdenv-ssh: The product image.  Full virtual dev environment over SSH.
#
# Extends dind-sshd with developer tools, git, C/C++ toolchain, and a
# default ``python3`` executable (via ``uv python install --default``).

ARG BASE_TAG=latest
FROM dind-sshd:${BASE_TAG}

# Create python/python3 symlinks pointing to the already-installed 3.13.
USER dockeruser
RUN uv python install --default 3.13
USER root

RUN apk update && apk add --no-cache \
 git \
 gcc \
 g++ \
 musl-dev \
 make \
 curl \
 jq \
 ripgrep \
 inotify-tools \
 nodejs \
 npm

# start-sshd.sh entrypoint requires root for chown, sshd, etc.
USER root
WORKDIR /home/dockeruser
