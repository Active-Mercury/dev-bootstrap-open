"""CLI to create and manage vdenv Docker development-environment containers.

Computes SSH port, volume names, and git mount paths from the project
path, then starts a ``--privileged`` container with ``--restart
unless-stopped``.
"""

import argparse
from argparse import ArgumentParser
from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import os
import os.path
from pathlib import Path
from pathlib import PurePosixPath
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Final

from vdenv.mount_args import calculate_mount_args
from vdenv.mount_args import MountResult


DEFAULT_IMAGE: Final[str] = "vdenv-ssh:latest"
CONTAINER_CODE_PATH: Final[PurePosixPath] = PurePosixPath("/home/dockeruser/code")
DOCKER_LIB_VOLUME_SUFFIX: Final[str] = "_lib_docker"
UV_CACHE_VOLUME_SUFFIX: Final[str] = "_uv_cache"
UV_CACHE_CONTAINER_PATH: Final[str] = "/home/dockeruser/.cache/uv"
PORT_RANGE_START: Final[int] = 10000
PORT_RANGE_END: Final[int] = 60000
SSH_CONFIG_HOST_PREFIX: Final[str] = "vdenv-"
_BEGIN_MARKER: Final[str] = "# BEGIN vdenv: "
_END_MARKER: Final[str] = "# END vdenv: "
_GIT_CONFIG_KEYS_TO_PROPAGATE: Final[tuple[str, ...]] = (
    "user.name",
    "user.email",
    "core.autocrlf",
    "core.filemode",
    "init.defaultbranch",
    "pull.rebase",
)


@dataclass(frozen=True)
class ContainerIdentity:
    """Deterministic identity derived from a project path."""

    name: str
    path_hash: str
    container_name: str
    ssh_port: int
    docker_volume: str
    uv_cache_volume: str


def console_entry() -> None:
    """Console-script entry point that delegates to :func:`main`."""
    sys.exit(main(tuple(sys.argv[1:]), sys.argv[0], __name__))


def main(cmd_args: Sequence[str], prog_path: str, entry_name: str) -> int:
    """Execute the command-line interface.

    :param cmd_args: Command arguments for the program.
    :type cmd_args: Sequence[str]
    :param str prog_path: The program path (i.e., sys.argv[0] or equivalent).
    :param str entry_name: The ``__name__`` of the calling module.
    :return: Exit code (0 for success, non-zero for failure).
    :rtype: int
    """
    _ = entry_name
    parser = _get_parser(os.path.basename(prog_path))
    parsed = parser.parse_args(cmd_args)

    host_path = _resolve_host_path(parsed.host_repo_path)
    repo_type, toplevel = _classify_repo(host_path)

    if repo_type == "C" and not parsed.allow_non_git_repo:
        return _err(
            f"Not a git repository: {host_path}\n"
            "Pass --allow-non-git-repo to mount a plain directory."
        )
    if parsed.rw_git and repo_type != "A":
        return _err("--rw-git is only valid for Type A (toplevel git repo).")

    path_for_hash = host_path
    if repo_type == "A" and toplevel is not None:
        path_for_hash = toplevel
    identity = _compute_identity(
        path_for_hash,
        parsed.port,
        parsed.suffix,
    )

    if parsed.info:
        _print_info(identity, host_path, repo_type)
        return 0

    mount_info = _build_repo_mounts(
        host_path, repo_type, toplevel, rw_git=parsed.rw_git
    )

    if parsed.sync:
        if not _container_exists(identity.container_name):
            return _err(f"Container '{identity.container_name}' does not exist.")
        _sync_git_config(identity.container_name)
        print(f"Git config synced to {identity.container_name}")
        return 0

    return _create_container(
        identity=identity,
        mount_info=mount_info,
        image=parsed.image,
        force=parsed.force,
        dry_run=parsed.dry_run,
        public_key_file=parsed.public_key,
        extra_volumes=parsed.extra_volume or [],
    )


def _get_parser(prog_name: str) -> ArgumentParser:
    parser = ArgumentParser(
        prog=prog_name,
        description=(
            "Create and manage vdenv Docker development-environment "
            "containers tied to git repositories."
        ),
        formatter_class=lambda prog: argparse.HelpFormatter(prog, width=80),
    )
    parser.add_argument(
        "host_repo_path",
        nargs="?",
        default=None,
        help="Path to the git repository on the host (default: cwd).",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=None,
        help=("Override SSH port (default: deterministic from path hash)."),
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Docker image to use (default: {DEFAULT_IMAGE}).",
    )
    parser.add_argument(
        "--public-key",
        default=None,
        help="Path to SSH public key file for dockeruser.",
    )
    parser.add_argument(
        "--suffix",
        default=None,
        help="Suffix appended to container name and volume names.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        default=False,
        help="Force-remove existing container before starting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the docker run command without executing it.",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        default=False,
        help="Print computed names/ports without starting.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        default=False,
        help="Sync host git config into an existing container.",
    )
    parser.add_argument(
        "--rw-git",
        action="store_true",
        default=False,
        help="Mount .git read-write instead of read-only (Type A only).",
    )
    parser.add_argument(
        "--allow-non-git-repo",
        action="store_true",
        default=False,
        help="Allow mounting a directory that is not a git repository.",
    )
    parser.add_argument(
        "--extra-volume",
        action="append",
        default=None,
        help=(
            "Extra -v argument grafted into docker run "
            "(repeatable, e.g. --extra-volume /host:/ctr)."
        ),
    )
    return parser


def _resolve_host_path(raw: str | None) -> Path:
    """Resolve and validate the host path.

    Expands environment variables (``%VAR%`` / ``$VAR``) and ``~``
    before resolving, so that shell-style paths work on all platforms.

    :param raw: User-supplied path, or ``None`` for cwd.
    :type raw: str | None
    :return: Resolved absolute path.
    :rtype: Path
    """
    if raw:
        expanded = os.path.expandvars(os.path.expanduser(raw))
        candidate = Path(expanded).resolve()
    else:
        candidate = Path.cwd().resolve()
    if not candidate.is_dir():
        sys.stderr.write(f"error: not a directory: {candidate}\n")
        sys.exit(1)
    return candidate


def _classify_repo(host_path: Path) -> tuple[str, Path | None]:
    """Determine repository type (A, B, or C).

    :param Path host_path: Resolved directory path.
    :return: ``("A", toplevel)``, ``("B", toplevel)``, or ``("C", None)``.
    :rtype: tuple[str, Path | None]
    """
    result = subprocess.run(
        ["git", "-C", str(host_path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return "C", None

    toplevel = Path(result.stdout.strip()).resolve()
    if toplevel == host_path:
        return "A", toplevel
    return "B", toplevel


def _compute_identity(
    path_for_hash: Path,
    port_override: int | None,
    suffix: str | None,
) -> ContainerIdentity:
    """Derive deterministic names and ports from a canonical path.

    :param Path path_for_hash: Path used for hashing.
    :param port_override: Explicit SSH port, or ``None``.
    :type port_override: int | None
    :param suffix: Optional suffix for names.
    :type suffix: str | None
    :return: All computed identifiers.
    :rtype: ContainerIdentity
    """
    canonical = str(path_for_hash).replace("\\", "/")
    path_hash = hashlib.blake2b(canonical.encode(), digest_size=4).hexdigest()
    name = path_for_hash.name
    suffix_part = f"-{suffix}" if suffix else ""
    identity_prefix = f"{name}{suffix_part}-{path_hash}"

    if port_override is not None:
        ssh_port = port_override
    else:
        hash_int = int(path_hash, 16)
        ssh_port = PORT_RANGE_START + (hash_int % (PORT_RANGE_END - PORT_RANGE_START))

    return ContainerIdentity(
        name=name,
        path_hash=path_hash,
        container_name=f"vdenv-ssh-{identity_prefix}",
        ssh_port=ssh_port,
        docker_volume=f"{identity_prefix}{DOCKER_LIB_VOLUME_SUFFIX}",
        uv_cache_volume=f"{identity_prefix}{UV_CACHE_VOLUME_SUFFIX}",
    )


@dataclass(frozen=True)
class _MountInfo:
    """Collected mount arguments and container repo path."""

    mount_result: MountResult | None
    plain_volume_args: tuple[str, ...]
    container_repo_path: PurePosixPath
    rw_git: bool


def _build_repo_mounts(
    host_path: Path,
    repo_type: str,
    toplevel: Path | None,
    *,
    rw_git: bool,
) -> _MountInfo:
    """Build volume-mount arguments based on repo type.

    :param Path host_path: Resolved host directory.
    :param str repo_type: One of ``"A"``, ``"B"``, ``"C"``.
    :param toplevel: Git toplevel, or ``None`` for type C.
    :type toplevel: Path | None
    :param bool rw_git: Mount ``.git`` read-write.
    :return: Mount information.
    :rtype: _MountInfo
    """
    if repo_type == "A" and toplevel is not None:
        mr = calculate_mount_args(toplevel, CONTAINER_CODE_PATH)
        return _MountInfo(
            mount_result=mr,
            plain_volume_args=(),
            container_repo_path=mr.container_repo_path,
            rw_git=rw_git,
        )

    container_path = CONTAINER_CODE_PATH / host_path.name
    vol = ("-v", f"{host_path}:{container_path}")
    return _MountInfo(
        mount_result=None,
        plain_volume_args=vol,
        container_repo_path=container_path,
        rw_git=False,
    )


def _print_info(identity: ContainerIdentity, host_path: Path, repo_type: str) -> None:
    """Print computed identity in read-only mode.

    :param identity: Computed container identity.
    :type identity: ContainerIdentity
    :param Path host_path: Resolved host path.
    :param str repo_type: Repository type classification.
    """
    alias = f"{SSH_CONFIG_HOST_PREFIX}{identity.container_name}"
    print(f"Host path:       {host_path}")
    print(f"Repo type:       {repo_type}")
    print(f"Container name:  {identity.container_name}")
    print(f"SSH host alias:  {alias}")
    print(f"SSH port:        {identity.ssh_port}")
    print(f"Docker volume:   {identity.docker_volume}")
    print(f"uv cache vol:    {identity.uv_cache_volume}")


def _create_container(
    *,
    identity: ContainerIdentity,
    mount_info: _MountInfo,
    image: str,
    force: bool,
    dry_run: bool,
    public_key_file: str | None,
    extra_volumes: list[str],
) -> int:
    """Build and optionally execute the ``docker run`` command.

    :param identity: Computed container identity.
    :type identity: ContainerIdentity
    :param mount_info: Mount arguments for the repository.
    :type mount_info: _MountInfo
    :param str image: Docker image name.
    :param bool force: Force-remove existing container first.
    :param bool dry_run: Print command without executing.
    :param public_key_file: SSH public key file path, or ``None``.
    :type public_key_file: str | None
    :param extra_volumes: Additional ``-v`` arguments.
    :type extra_volumes: list[str]
    :return: Exit code.
    :rtype: int
    """
    with tempfile.TemporaryDirectory() as tempdir:
        repo_vol_args = _resolve_repo_vol_args(mount_info, Path(tempdir))
        env_args = _build_env_args(identity, public_key_file)
        extra_vol_args = _build_extra_vol_args(extra_volumes)

        cmd: list[str] = [
            "docker",
            "run",
            "--privileged",
            "-d",
            "--restart",
            "unless-stopped",
            "--name",
            identity.container_name,
            "-p",
            f"{identity.ssh_port}:22",
            "-v",
            f"{identity.docker_volume}:/var/lib/docker",
            "-v",
            f"{identity.uv_cache_volume}:{UV_CACHE_CONTAINER_PATH}",
            *env_args,
            *repo_vol_args,
            *extra_vol_args,
            image,
        ]

        if dry_run:
            print(shlex.join(cmd))
            return 0

        if force:
            _remove_container_if_exists(identity.container_name)
        elif _container_exists(identity.container_name):
            return _err(
                f"Container '{identity.container_name}' already exists. "
                "Use --force to replace it."
            )

        _ensure_volume(identity.docker_volume)
        _ensure_volume(identity.uv_cache_volume)

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return _err(f"docker run failed:\n{result.stderr.strip()}")

    cid = result.stdout.strip()[:12]
    print(f"Container started: {identity.container_name} ({cid})")
    print(f"  SSH port:        {identity.ssh_port}")
    print(f"  Docker volume:   {identity.docker_volume}")
    print(f"  Repo mounted:    {mount_info.container_repo_path}")

    _wait_for_docker_daemon(identity.container_name)
    _chown_uv_cache(identity.container_name)
    _sync_git_config(identity.container_name)
    _fetch_and_add_host_keys(identity.container_name, identity.ssh_port)
    _update_ssh_config(identity, public_key_file)

    return 0


def _resolve_repo_vol_args(mount_info: _MountInfo, tempdir: Path) -> list[str]:
    """Build ``-v`` flags for the repository mount.

    For Type A, produces args from the stored :class:`MountResult` with
    the desired ro/rw policy.  For Types B/C, returns the pre-computed
    plain bind-mount.

    :param mount_info: Repository mount information.
    :type mount_info: _MountInfo
    :param Path tempdir: Scratch directory for overlay files.
    :return: List of ``-v`` flag strings.
    :rtype: list[str]
    """
    if mount_info.mount_result is not None:
        return list(
            _volume_args_with_policy(
                mount_info.mount_result, mount_info.rw_git, tempdir
            )
        )
    return list(mount_info.plain_volume_args)


def _volume_args_with_policy(
    mount_result: MountResult,
    rw_git: bool,
    tempdir: Path,
) -> tuple[str, ...]:
    """Produce ``-v`` flags with the correct ro/rw policy.

    Worktree is always rw.  The ``.git`` entry (directory for normal
    clones, gitlink file for worktrees/submodules) is protected ro by
    default so that the SSH user cannot damage the host repo beyond
    what ``git reset --hard && git clean -fd`` can undo.

    :param mount_result: Calculated mount result.
    :type mount_result: MountResult
    :param bool rw_git: Mount ``.git`` read-write.
    :param Path tempdir: Scratch directory for overlay files.
    :return: Tuple of ``-v`` flag strings.
    :rtype: tuple[str, ...]
    """
    ctr_git_path = mount_result.worktree.container_path / ".git"
    args: list[str] = [
        "-v",
        (f"{mount_result.worktree.host_path}:{mount_result.worktree.container_path}"),
    ]
    if mount_result.git_dir is not None:
        git_suffix = "" if rw_git else ":ro"
        args.extend(
            [
                "-v",
                (
                    f"{mount_result.git_dir.host_path}"
                    f":{mount_result.git_dir.container_path}{git_suffix}"
                ),
            ]
        )
    if mount_result.overlay_git_content is not None:
        overlay_file = tempdir / ".git-overlay"
        overlay_file.write_text(mount_result.overlay_git_content, encoding="utf-8")
        args.extend(["-v", f"{overlay_file}:{ctr_git_path}:ro"])
    elif not rw_git:
        host_git = mount_result.worktree.host_path / ".git"
        args.extend(["-v", f"{host_git}:{ctr_git_path}:ro"])
    return tuple(args)


def _build_env_args(
    identity: ContainerIdentity, public_key_file: str | None
) -> list[str]:
    """Build ``-e`` flags for ``docker run``.

    :param identity: Computed container identity.
    :type identity: ContainerIdentity
    :param public_key_file: SSH public key path, or ``None``.
    :type public_key_file: str | None
    :return: List of ``-e`` flag strings.
    :rtype: list[str]
    """
    _ = identity
    args: list[str] = []
    if public_key_file is not None:
        pub_key = Path(public_key_file).expanduser().read_text().strip()
        args.extend(["-e", f"DOCKERUSER_PUBLIC_KEY={pub_key}"])
    return args


def _build_extra_vol_args(extra_volumes: list[str]) -> list[str]:
    """Convert ``--extra-volume`` values into ``-v`` pairs.

    :param extra_volumes: Raw volume specifications.
    :type extra_volumes: list[str]
    :return: Flattened ``-v`` flag strings.
    :rtype: list[str]
    """
    args: list[str] = []
    for vol in extra_volumes:
        args.extend(["-v", vol])
    return args


def _container_exists(name: str) -> bool:
    """Check whether a container with the given name exists.

    :param str name: Container name.
    :return: ``True`` if the container exists.
    :rtype: bool
    """
    result = subprocess.run(
        ["docker", "container", "inspect", name],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return result.returncode == 0


def _remove_container_if_exists(name: str) -> None:
    """Remove a container if it exists.

    :param str name: Container name.
    """
    subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _ensure_volume(volume_name: str) -> None:
    """Create a Docker volume if it does not already exist.

    :param str volume_name: Name of the volume.
    """
    subprocess.run(
        ["docker", "volume", "create", volume_name],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )


def _wait_for_docker_daemon(container_name: str) -> None:
    """Wait until the nested Docker daemon is ready.

    :param str container_name: Name of the running container.
    """
    sys.stdout.write("Waiting for Docker daemon...")
    sys.stdout.flush()
    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", container_name, "docker", "info"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode == 0:
            print(" ready.")
            return
        time.sleep(1.0)
    print(" timed out (container may still be starting).")


def _chown_uv_cache(container_name: str) -> None:
    """Ensure dockeruser owns the uv cache mount point.

    :param str container_name: Name of the running container.
    """
    subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "chown",
            "-R",
            "dockeruser:dockeruser",
            "/home/dockeruser/.cache",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _sync_git_config(container_name: str) -> None:
    """Propagate host git config into the container.

    Marks all directories as safe and copies a curated set of config keys from the
    host's effective git configuration.

    :param str container_name: Name of the running container.
    """
    subprocess.run(
        [
            "docker",
            "exec",
            "-u",
            "dockeruser",
            container_name,
            "git",
            "config",
            "--global",
            "--add",
            "safe.directory",
            "*",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    propagated: list[str] = []
    for key in _GIT_CONFIG_KEYS_TO_PROPAGATE:
        value = _get_host_git_config(key)
        if value is None:
            continue
        subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                "dockeruser",
                container_name,
                "git",
                "config",
                "--global",
                key,
                value,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        propagated.append(key)

    if propagated:
        print(f"  git config:      propagated {', '.join(propagated)}")


def _get_host_git_config(key: str) -> str | None:
    """Read a git config value from the host.

    :param str key: Git config key.
    :return: The value, or ``None`` if unset.
    :rtype: str | None
    """
    result = subprocess.run(
        ["git", "config", "--get", key],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _update_ssh_config(
    identity: ContainerIdentity, public_key_file: str | None
) -> None:
    """Add or update a managed Host block in ``~/.ssh/config``.

    Always writes a config block so the container is immediately
    visible to SSH clients (e.g. Cursor Remote-SSH).  When
    *public_key_file* is provided, an ``IdentityFile`` line is included.

    :param identity: Computed container identity.
    :type identity: ContainerIdentity
    :param public_key_file: Path to the public key, or ``None``.
    :type public_key_file: str | None
    """
    alias = f"{SSH_CONFIG_HOST_PREFIX}{identity.container_name}"

    block_lines = [
        f"{_BEGIN_MARKER}{alias}",
        f"Host {alias}",
        "    HostName localhost",
        f"    Port {identity.ssh_port}",
        "    User dockeruser",
    ]
    if public_key_file is not None:
        pub_path = Path(public_key_file).expanduser().resolve()
        priv_path = pub_path.parent / pub_path.stem
        if pub_path.suffix == ".pub" and priv_path.exists():
            identity_file = _normalize_to_home(priv_path)
        else:
            identity_file = _normalize_to_home(pub_path)
        block_lines.append(f"    IdentityFile {identity_file}")
    block_lines.extend(
        [
            "    StrictHostKeyChecking no",
            "    UserKnownHostsFile /dev/null",
            f"{_END_MARKER}{alias}",
        ]
    )
    block_text = "\n".join(block_lines)

    ssh_config = Path.home() / ".ssh" / "config"
    ssh_config.parent.mkdir(parents=True, exist_ok=True)

    content = ""
    if ssh_config.exists():
        content = ssh_config.read_text(encoding="utf-8")

    begin_tag = f"{_BEGIN_MARKER}{alias}"
    end_tag = f"{_END_MARKER}{alias}"
    begin_idx = content.find(begin_tag)
    end_idx = content.find(end_tag)

    if begin_idx != -1 and end_idx != -1:
        end_idx += len(end_tag)
        if end_idx < len(content) and content[end_idx] == "\n":
            end_idx += 1
        content = content[:begin_idx] + block_text + "\n" + content[end_idx:]
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        if content:
            content += "\n"
        content += block_text + "\n"

    ssh_config.write_text(content, encoding="utf-8")
    print(f"  SSH config:      Host {alias}")


def _normalize_to_home(path: Path) -> str:
    """Return *path* with ``~/`` prefix if it is under the home directory.

    :param Path path: Absolute resolved path.
    :return: Possibly ``~/``-prefixed path string.
    :rtype: str
    """
    home = Path.home()
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


def _fetch_and_add_host_keys(container_name: str, ssh_port: int) -> None:
    """Fetch SSH host keys from the container and add to known_hosts.

    :param str container_name: Name of the running container.
    :param int ssh_port: Published SSH port on localhost.
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "sh",
            "-c",
            "cat /etc/ssh/ssh_host_*_key.pub",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        sys.stderr.write("warning: could not read host keys from container\n")
        return

    host_entry = f"[localhost]:{ssh_port}"
    new_lines: list[str] = []
    for raw_line in result.stdout.strip().splitlines():
        parts = raw_line.split()
        if len(parts) >= 2:
            new_lines.append(f"{host_entry} {parts[0]} {parts[1]}")

    if not new_lines:
        return

    known_hosts = Path.home() / ".ssh" / "known_hosts"
    known_hosts.parent.mkdir(parents=True, exist_ok=True)

    existing: list[str] = []
    if known_hosts.exists():
        existing = [
            line
            for line in known_hosts.read_text(encoding="utf-8").splitlines()
            if not line.startswith(f"{host_entry} ")
        ]

    existing.extend(new_lines)
    known_hosts.write_text("\n".join(existing) + "\n", encoding="utf-8")
    print(f"  known_hosts:     updated ({len(new_lines)} keys for {host_entry})")


def _err(message: str) -> int:
    """Print an error message to stderr and return exit code 1.

    :param str message: Error message.
    :return: Exit code 1.
    :rtype: int
    """
    sys.stderr.write(f"error: {message}\n")
    return 1


if __name__ == "__main__":
    console_entry()
