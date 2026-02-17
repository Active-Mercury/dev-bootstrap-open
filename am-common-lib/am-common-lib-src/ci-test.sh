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

CI_COMMIT="${1:?Error: a commit hash argument is required.}"

git clone "file://${REPO_ROOT}" /home/dockeruser/git_repos/dev-bootstrap
cd ~/git_repos/dev-bootstrap
git checkout "$CI_COMMIT"

COMMIT=$(git rev-parse HEAD)
echo "At commit: $COMMIT"
# Out of an abundance of caution, me make sure the tree hash we will report
# is the correct one.
require_clean "Inexplicably, the working tree is not clean at this point."
TREE_HASH=$(git rev-parse HEAD^{tree})
echo "At tree: $TREE_HASH"

cd ~/git_repos/dev-bootstrap/am-common-lib/am-common-lib-src
uv sync

# -----------------------------------------------------------------------------
# Reformat and style checks
# -----------------------------------------------------------------------------

uv run fflint
require_clean "Formatter/linter has produced changes. Was 'fflint' not run locally?"

# -----------------------------------------------------------------------------
# Packaging test – build, install into a fresh venv, and verify
# -----------------------------------------------------------------------------
echo "==> Running packaging tests..."

PKG_TEST_REPO=~/git_repos/am-common-lib-pkg-test
git clone "file://${REPO_ROOT}" "$PKG_TEST_REPO"
cd "$PKG_TEST_REPO"
git checkout "$CI_COMMIT"

# Build the package following the steps documented in README.md
cd "$PKG_TEST_REPO/am-common-lib/am-common-lib-src"
uv build

# Create a completely fresh virtual environment (no dev dependencies)
PKG_VENV=~/pkg_test_venv/.venv
"$(uv python find 3.13)" -m venv "$PKG_VENV"

# Install only the built wheel
"$PKG_VENV/bin/pip" install dist/am_common_lib-*.whl

# Run the packaging sanity tests with the fresh venv's Python
"$PKG_VENV/bin/python" "$PKG_TEST_REPO/am-common-lib/am-common-lib-src/resources/test_install.py" -v

# -----------------------------------------------------------------------------
# Run tests with coverage
# -----------------------------------------------------------------------------
cd ~/git_repos/dev-bootstrap/am-common-lib/am-common-lib-src

echo "==> Running pytest with coverage report (term-missing + HTML)..."
mkdir -p reports

uv run pytest -v devenv-test \
  --junitxml=reports/junit_devenv-test.xml \
  --html=reports/pytest_devenv-test.html \
  --self-contained-html

uv run pytest -v \
  --cov=am_common_lib \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=html:reports/htmlcov \
  --cov-report=xml:reports/coverage.xml \
  --junitxml=reports/junit_am_common_lib.xml \
  --html=reports/pytest_am_common_lib.html \
  --self-contained-html

tar czf reports_"$(date +%Y%m%d)_${TREE_HASH}".tar.gz reports
