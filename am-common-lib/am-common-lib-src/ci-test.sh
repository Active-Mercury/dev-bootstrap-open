#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

source ~/.bashrc

require_clean() {
  local err_msg="$1"
  local status
  status="$(git status --porcelain)"
  if [ -n "$status" ]; then
    echo "Error: ${err_msg}" >&2
    echo "Uncommitted changes:" >&2
    echo "$status" >&2
    exit 1
  fi
}

# -----------------------------------------------------------------------------
# Pre‑flight checks
# -----------------------------------------------------------------------------

if [ -z "${DIND_FOR_CI-}" ]; then
  echo "Error: This script must be run inside a dind-dev container." >&2
  exit 1
fi

if [ "$(id -un)" != "dockeruser" ]; then
  echo "Error: This script must be run as 'dockeruser'." >&2
  exit 1
fi

# -----------------------------------------------------------------------------
# Set up the container
# -----------------------------------------------------------------------------
mkdir -p /home/dockeruser/git_repos

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"

git clone \
  "file://${REPO_ROOT}" \
  /home/dockeruser/git_repos/dev-bootstrap
cd ~/git_repos/dev-bootstrap
if [ -n "${1-}" ]; then
  git checkout "$1"
fi

COMMIT=$(git rev-parse HEAD)
echo "At commit: $COMMIT"
# Out of an abundance of caution, me make sure the tree hash we will report
# is the correct one.
require_clean "Inexplicably, the working tree is not clean at this point."
TREE_HASH=$(git rev-parse HEAD^{tree})
echo "At tree: $TREE_HASH"

cd ~/git_repos/dev-bootstrap/am-common-lib/am-common-lib-src
pipenv sync --dev

# -----------------------------------------------------------------------------
# Reformat and style checks
# -----------------------------------------------------------------------------

pipenv run format
require_clean "Reformatting has produced changes. Was 'format' not run?"
pipenv run chk

# -----------------------------------------------------------------------------
# Run tests with coverage
# -----------------------------------------------------------------------------
echo "==> Running pytest with coverage report (term-missing + HTML)..."
mkdir -p reports

pipenv run pytest -v devenv-test \
  --junitxml=reports/junit_devenv-test.xml \
  --html=reports/pytest_devenv-test.html \
  --self-contained-html

pipenv run pytest -v \
  --cov=am_common_lib \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=html:reports/htmlcov \
  --cov-report=xml:reports/coverage.xml \
  --junitxml=reports/junit_am_common_lib.xml \
  --html=reports/pytest_am_common_lib.html \
  --self-contained-html

tar czf reports_"$(date +%Y%m%d)_${TREE_HASH}".tar.gz reports
