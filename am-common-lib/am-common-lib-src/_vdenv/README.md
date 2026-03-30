# vdenv -- Virtual Development Environments

> **Status: pre-release (not even beta).** The functionality exercised by the
> test suite is likely to be retained, but there may be breaking changes to the
> CLI, image layout, or mount semantics at any time.

`vdenv` provides Docker-based virtual development environments accessible over
SSH. Each environment is a privileged container running a nested Docker daemon,
an OpenSSH server, and a curated set of developer tools. The host repository is
bind-mounted into the container so that code edits are immediately visible on
both sides.

## Image Chain

The Docker images form a three-layer chain. Each layer extends the previous one:

| Image         | Base                   | Adds                                                                         |
| ------------- | ---------------------- | ---------------------------------------------------------------------------- |
| **dind-uv**   | `docker:dind` (Alpine) | Bash, `dockeruser`, Astral `uv`, Python 3.9/3.11/3.13                        |
| **dind-sshd** | `dind-uv`              | OpenSSH daemon, public-key auth, `start-sshd.sh` entrypoint                  |
| **vdenv-ssh** | `dind-sshd`            | git, gcc/g++, make, curl, jq, ripgrep, Node.js/npm, default `python3` (3.13) |

## Installing the CLI

From the repository root:

```bash
cd am-common-lib/am-common-lib-src
uv sync
```

This installs `vdenv-mgmt` into the project's virtual environment. You can then
run it via `uv run vdenv-mgmt` from within the project directory, or create a
symlink so it is available globally:

```bash
ln -sf "$(pwd)/.venv/bin/vdenv-mgmt" ~/bin/vdenv-mgmt
```

After symlinking, `vdenv-mgmt` is on your PATH and can be invoked from any
directory.

## Building the Docker Images

Build the images in order from the `_vdenv/src/vdenv/resources/` directory. Each
build must be run from the directory containing the Dockerfile:

```bash
RESOURCES=_vdenv/src/vdenv/resources

docker build -t dind-uv:latest "$RESOURCES/dind-uv"
docker build -t dind-sshd:latest "$RESOURCES/dind-sshd"
docker build -t vdenv-ssh:latest "$RESOURCES/vdenv-ssh"
```

## CLI Usage

```bash
# Show computed names/ports for a repository
vdenv-mgmt /path/to/repo --info

# Preview the docker run command without executing
vdenv-mgmt /path/to/repo --dry-run

# Create a container (force-replace if one exists)
vdenv-mgmt /path/to/repo --force

# Sync host git config into a running container
vdenv-mgmt /path/to/repo --sync
```

The CLI determines container names, SSH ports, and volume names
deterministically from the repository path. Containers are created with
`--restart unless-stopped` so they survive host reboots.

Run `vdenv-mgmt --help` for the full set of options.

## Running the Tests

From `am-common-lib/am-common-lib-src`:

```bash
# Unit tests only (no Docker required)
uv run pytest test/vdenv/test_mount_args.py
uv run pytest test/vdenv/test_cli.py

# Full suite including Docker image integration tests
# (requires the three images to be built locally)
uv run pytest test/vdenv/
```

The image integration tests will be skipped automatically if Docker is not
available or the required images have not been built.
