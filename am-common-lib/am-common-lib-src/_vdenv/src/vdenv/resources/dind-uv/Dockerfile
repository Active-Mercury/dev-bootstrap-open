# dind-uv: Docker-in-Docker with Astral uv and managed CPython versions.
#
# Base is docker:dind (Alpine).  uv is installed via its official install
# script.  Python interpreters come from ``uv python install`` (standalone
# builds that bundle ssl, sqlite3, etc.).  No system Python is used.

FROM docker:dind

RUN apk add --no-cache bash

RUN adduser -D -h /home/dockeruser -s /bin/bash -g "" dockeruser \
 && addgroup dockeruser docker

ENV PATH="/home/dockeruser/.local/bin:$PATH"

USER dockeruser
WORKDIR /home/dockeruser

RUN wget -qO- https://astral.sh/uv/install.sh | sh \
 && uv python install 3.9 3.11 3.13 \
 && printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >>~/.bashrc \
 && printf 'export PATH="$HOME/.local/bin:$PATH"\n' >>~/.profile

# The docker:dind entrypoint (dockerd-entrypoint.sh) must run as root.
USER root
