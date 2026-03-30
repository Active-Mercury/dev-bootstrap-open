# dind-sshd: Adds an OpenSSH daemon to dind-uv.
#
# At container start the entrypoint:
#   1. Installs the public key from DOCKERUSER_PUBLIC_KEY.
#   2. Starts the nested Docker daemon in the background.
#   3. Hardens and starts sshd in the foreground.
#
# The container must be run with --privileged for the nested daemon to work.

ARG BASE_TAG=latest
FROM dind-uv:${BASE_TAG}

USER root

RUN apk update \
  && apk add --no-cache openssh \
  && mkdir -p /var/run/sshd \
  && mkdir -p /etc/ssh/authorized_keys

ADD mark_bash_init.py /opt/dind-sshd/mark_bash_init.py
RUN chown root:root /opt/dind-sshd/mark_bash_init.py \
  && chmod 0644 /opt/dind-sshd/mark_bash_init.py

ADD start-sshd.sh /usr/local/bin/start-sshd.sh
RUN chmod +x /usr/local/bin/start-sshd.sh

EXPOSE 22

ENTRYPOINT ["/usr/local/bin/start-sshd.sh"]
