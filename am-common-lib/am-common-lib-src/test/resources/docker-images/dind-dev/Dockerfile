FROM docker:dind

RUN apk update && apk add --no-cache \
 shadow \
 git \
 python3 \
 py3-pip \
 bash
RUN adduser --disabled-password \
 --gecos "" \
 --home /home/dockeruser \
 --shell /bin/bash \
 dockeruser \
 && usermod -aG docker dockeruser

USER dockeruser
WORKDIR /home/dockeruser

ENV DIND_FOR_CI=1

RUN pip install --break-system-packages pipenv \
 && mkdir -p /home/dockeruser/bin \
 && ln -sf "/home/dockeruser/.local/bin/pipenv" /home/dockeruser/bin/pipenv \
 && echo 'export PATH="~/bin:$PATH"' >>/home/dockeruser/.bashrc

USER root
