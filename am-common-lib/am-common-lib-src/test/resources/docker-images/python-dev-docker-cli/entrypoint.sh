#!/bin/bash

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: setting a user via docker is not supported. Any user specification must be part of CMD." >&2
  exit 1
fi

DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
GROUP_NAME=$(getent group "${DOCKER_GID}" | cut -d: -f1 || echo root)
usermod -aG "${GROUP_NAME}" dockeruser

USER=dockeruser
# Parse optional -u|--user <user>
if [ "$#" -ge 2 ] && { [ "$1" = "-u" ] || [ "$1" = "--user" ]; }; then
  USER=$2
  shift 2
fi

# Skip -- separator if present
if [ "$1" = "--" ]; then
  shift
fi

# Ensure there's something left to run
if [ "$#" -lt 1 ]; then
  cat << EOF >&2
Error: no command specified.

Usage: $0 [-u|--user <user>] [--] <command> [args...]
  -u, --user <user>   run the command as this user (default: dockeruser)
  --                  end of options; what follows is the command to run
EOF
  exit 1
fi

# Exec the desired command as $USER
exec runuser -u "$USER" -- "$@"
