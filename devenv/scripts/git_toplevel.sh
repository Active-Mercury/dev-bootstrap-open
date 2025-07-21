#!/usr/bin/env bash
#
# Locate the top-level directory (repository root) of the current Git repository
# and optionally run commands there.

if [[ "${1-:-}" == "--" ]]; then
  shift
  (cd "$(git rev-parse --show-toplevel)" && exec "$@")
elif [[ "$#" -eq 0 ]]; then
  # (cd "$(git rev-parse --show-toplevel)" && pwd)
  git rev-parse --show-toplevel
elif [[ "$1" = "--help" || "$1" = "-h" ]]; then
  cat << EOF
Usage: $(basename "$0") [-h] [<git-command> [args...] | -- <command> [args...]]

Without arguments:
  Prints the top-level directory of the current Git repository.

When first argument is "--":
  Executes the specified command(s) in the repository root.
  Example: $(basename "$0") -- make build

Otherwise:
  Runs "git <args>" in the repository root.
  Example: $(basename "$0") status

Options:
  -h, --help    Show this help message and exit.
EOF
else
  (cd "$(git rev-parse --show-toplevel)" && git "$@")
fi
