#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Run the CI workflow locally inside the dind-dev container."""

from __future__ import annotations

import argparse
from argparse import ArgumentParser
from collections import defaultdict
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import hashlib
import json
import os
import os.path
from pathlib import Path
from pathlib import PurePosixPath
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Final, TextIO


# Python 3.9 compatibility: UTC was added in Python 3.11
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc  # noqa: UP017


MOUNTED_BASE_PATH: Final[PurePosixPath] = PurePosixPath("/home/dockeruser/src-git")
DOCKER_IMAGES_DIR: Final[Path] = (
    Path(__file__).resolve().parents[1] / "test" / "resources" / "docker-images"
)
CI_SCRIPT_REL_PATH: Final[PurePosixPath] = PurePosixPath("ci-test")
CONTAINER_REPO_CLONE_DIR: Final[PurePosixPath] = PurePosixPath(
    "/home/dockeruser/git_repos/dev-bootstrap/am-common-lib/am-common-lib-src"
)
UV_CACHE_CONTAINER_PATH: Final[str] = "/home/dockeruser/.cache/uv"
UV_DATA_CONTAINER_PATH: Final[str] = "/home/dockeruser/.local/share/uv"
_CI_TEMP_REF: Final[str] = "refs/heads/__ci_working_tree__"
GIT_WRITE_WORKING_TREE_SCRIPT: Final[Path] = (
    Path(__file__).resolve().parents[1]
    / "_devtools"
    / "src"
    / "_devtools"
    / "git_write_working_tree.py"
)


@dataclass(frozen=True)
class MountPath:
    """Host path and container path for a mount."""

    out_path: Path
    in_path: PurePosixPath


@dataclass(frozen=True)
class MountingArgs:
    """Calculated mounting paths and git metadata for the container."""

    worktree: MountPath
    git_dir: MountPath | None
    git_file_uses_absolute_path: bool
    worktree_git_dir_relative_path: Path | None


def main(cmd_args: Sequence[str], prog_path: str) -> None:
    """Execute the command-line interface.

    :param cmd_args: Command arguments for the program.
    :type cmd_args: Sequence[str]
    :param str prog_path: The program path (i.e., sys.argv[0] or equivalent).
    """
    parser = _get_parser(os.path.basename(prog_path))
    parsed_args = parser.parse_args(cmd_args)

    repo_root = _resolve_repo_root()
    _ensure_prerequisites()

    ci_commit, _, needs_ref_cleanup = _capture_working_tree_commit(repo_root)

    project_id = _compute_project_identity()
    container_name = parsed_args.container_name or project_id
    dind_volume = f"{project_id}_lib_docker"
    uv_cache_volume = f"{project_id}_uv_cache"
    uv_data_volume = f"{project_id}_uv_data"

    _ensure_volume_exists(dind_volume)
    _ensure_volume_exists(uv_cache_volume)
    _ensure_volume_exists(uv_data_volume)
    _build_host_dind_image()

    mounting_args = calculate_mounting_args(repo_root, MOUNTED_BASE_PATH)

    try:
        _run_local_ci(
            container_name=container_name,
            repo_root=repo_root,
            mounting_args=mounting_args,
            keep_container=parsed_args.keep_container,
            dind_volume=dind_volume,
            uv_cache_volume=uv_cache_volume,
            uv_data_volume=uv_data_volume,
            ci_commit=ci_commit,
        )
    finally:
        if needs_ref_cleanup:
            _cleanup_temp_ref(repo_root)


def calculate_mounting_args(
    git_repo_path: Path, mounted_base_path: PurePosixPath
) -> MountingArgs:
    """Calculate host-to-container mounting paths for worktree and git dir.

    :param Path git_repo_path: Path to the git worktree root.
    :param mounted_base_path: Base path inside the container where mounts live.
    :type mounted_base_path: PurePosixPath
    :return: Mounting arguments for worktree and optional overlay git directory.
    :rtype: MountingArgs
    """
    git_pointer = git_repo_path / ".git"
    if git_pointer.is_dir():
        return MountingArgs(
            worktree=MountPath(git_repo_path, mounted_base_path / "src-git-repo"),
            git_dir=None,
            git_file_uses_absolute_path=False,
            worktree_git_dir_relative_path=None,
        )

    if not git_pointer.is_file():
        raise RuntimeError(f"Expected .git to be a file or directory at {git_pointer}")

    git_file_target = _parse_git_file_target(git_pointer)
    git_file_uses_absolute_path = git_file_target.is_absolute()
    true_git_dir = _resolve_true_git_dir(git_repo_path)
    common_ancestor = _common_ancestor(git_repo_path, true_git_dir)
    worktree_in_path = mounted_base_path / PurePosixPath(
        *git_repo_path.relative_to(common_ancestor).parts
    )
    git_dir_in_path = mounted_base_path / PurePosixPath(
        *true_git_dir.relative_to(common_ancestor).parts
    )
    relative_path = Path(os.path.relpath(true_git_dir, git_repo_path))
    return MountingArgs(
        worktree=MountPath(git_repo_path, worktree_in_path),
        git_dir=MountPath(true_git_dir, git_dir_in_path),
        git_file_uses_absolute_path=git_file_uses_absolute_path,
        worktree_git_dir_relative_path=relative_path,
    )


def _get_parser(prog_name: str) -> ArgumentParser:
    parser = ArgumentParser(
        prog=prog_name,
        description="Run local CI in dind-dev and bundle reports in .ci-reports.",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, width=80),
    )
    parser.add_argument(
        "--container-name",
        default=None,
        help="Optional explicit dind container name.",
    )
    parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Keep the dind container after completion for debugging.",
    )
    return parser


def _resolve_repo_root() -> Path:
    """Resolve repository root from git metadata."""
    proc = _run_checked(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
    )
    return Path(proc.stdout.strip()).resolve()


def _compute_project_identity() -> str:
    """Compute a deterministic container name from the project folder path.

    :return: Container name in the form ``{folder_name}_{short_hash}``.
    :rtype: str
    """
    project_dir = Path(__file__).resolve().parents[1]
    path_hash = hashlib.blake2b(str(project_dir).encode(), digest_size=4).hexdigest()
    return f"{project_dir.name}_{path_hash}"


def _capture_working_tree_commit(repo_root: Path) -> tuple[str, int, bool]:
    """Obtain a commit whose tree matches the current working directory state.

    Runs ``git_write_working_tree.py`` to compute the tree hash that
    represents all tracked content (including uncommitted changes), then
    records ``unix_time_ms``.  If HEAD already points at this tree the
    HEAD commit is returned; otherwise a new commit object is created
    with ``git commit-tree`` and a temporary branch ref is created so
    that the commit is reachable during ``git clone file://...``.

    :param Path repo_root: Repository root directory.
    :return: ``(commit_hash, unix_time_ms, needs_ref_cleanup)``.
    :rtype: tuple[str, int, bool]
    """
    tree_hash = subprocess.run(
        [sys.executable, str(GIT_WRITE_WORKING_TREE_SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo_root),
    ).stdout.strip()
    unix_time_ms = time.time_ns() // 1_000_000

    head_tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo_root),
    ).stdout.strip()

    if head_tree == tree_hash:
        head_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(repo_root),
        ).stdout.strip()
        print(f"Working tree matches HEAD ({head_commit}).", flush=True)
        return head_commit, unix_time_ms, False

    commit_hash = subprocess.run(
        [
            "git",
            "commit-tree",
            tree_hash,
            "-p",
            "HEAD",
            "-m",
            f"ci: working-tree snapshot at {unix_time_ms}",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo_root),
    ).stdout.strip()

    subprocess.run(
        ["git", "update-ref", _CI_TEMP_REF, commit_hash],
        check=True,
        cwd=str(repo_root),
    )

    print(
        f"Created working-tree commit {commit_hash} (tree {tree_hash}, parent HEAD).",
        flush=True,
    )
    return commit_hash, unix_time_ms, True


def _cleanup_temp_ref(repo_root: Path) -> None:
    """Delete the temporary branch ref created for CI.

    :param Path repo_root: Repository root directory.
    """
    subprocess.run(
        ["git", "update-ref", "-d", _CI_TEMP_REF],
        check=False,
        cwd=str(repo_root),
        capture_output=True,
    )


def _ensure_prerequisites() -> None:
    """Verify required external tools are available."""
    for tool in ("docker", "git"):
        _run_checked([tool, "--version"], capture_output=True)


def _ensure_volume_exists(volume_name: str) -> None:
    """Create a Docker volume if it does not already exist.

    :param str volume_name: Name of the Docker volume to create.
    """
    _run_checked(["docker", "volume", "create", volume_name])


def _build_host_dind_image() -> None:
    """Build the host-side `dind-dev` image needed to launch local CI."""
    for image_name, image_dir in _active_image_build_plan(DOCKER_IMAGES_DIR):
        if image_name != "dind-dev":
            continue
        print(f"Building host image: {image_name} ({image_dir})", flush=True)
        _run_checked(["docker", "build", "-t", image_name, str(image_dir)])
        return
    raise RuntimeError("Could not find an active dind-dev image definition.")


def _run_local_ci(
    *,
    container_name: str,
    repo_root: Path,
    mounting_args: MountingArgs,
    keep_container: bool,
    dind_volume: str,
    uv_cache_volume: str,
    uv_data_volume: str,
    ci_commit: str,
) -> None:
    _stop_containers_using_volume(dind_volume)
    _stop_containers_using_volume(uv_cache_volume)
    _stop_containers_using_volume(uv_data_volume)
    _remove_container_if_exists(container_name)

    with tempfile.TemporaryDirectory() as tempdir:
        tempdir_path = Path(tempdir)
        log_path = tempdir_path / "ci_test.out"
        overlay_git_file = _create_overlay_git_file_if_needed(
            mounting_args, tempdir_path
        )
        overlay_ci_script = _create_overlay_ci_script_if_needed(repo_root, tempdir_path)
        mount_args = _build_mount_args(
            mounting_args=mounting_args,
            overlay_git_file=overlay_git_file,
            overlay_ci_script=overlay_ci_script,
        )

        _run_checked(
            [
                "docker",
                "run",
                "--privileged",
                "-d",
                "--name",
                container_name,
                "-v",
                f"{dind_volume}:/var/lib/docker",
                "-v",
                f"{uv_cache_volume}:{UV_CACHE_CONTAINER_PATH}",
                "-v",
                f"{uv_data_volume}:{UV_DATA_CONTAINER_PATH}",
                *mount_args,
                "dind-dev",
            ]
        )
        _run_checked(
            [
                "docker",
                "exec",
                container_name,
                "sh",
                "-c",
                "chown -R dockeruser:dockeruser"
                " /home/dockeruser/.cache /home/dockeruser/.local",
            ]
        )
        try:
            _wait_for_inner_docker(container_name)
            _build_inner_images(
                container_name=container_name,
                repo_in_container=mounting_args.worktree.in_path,
            )
            run_timestamp = datetime.now(UTC)
            ci_exit_code = _stream_ci_output(
                container_name=container_name,
                repo_in_container=mounting_args.worktree.in_path,
                log_path=log_path,
                ci_commit=ci_commit,
            )
            reports_file_path = _collect_and_bundle_results(
                container_name=container_name,
                repo_root=repo_root,
                ci_log_path=log_path,
                tempdir_path=tempdir_path,
                run_timestamp=run_timestamp,
                ci_passed=ci_exit_code == 0,
            )
            print(f"Created report bundle: {reports_file_path}", flush=True)
            if ci_exit_code != 0:
                sys.exit(ci_exit_code)
        finally:
            if keep_container:
                print(f"Container kept for debugging: {container_name}", flush=True)
            else:
                _remove_container_if_exists(container_name)


def _parse_git_file_target(git_file_path: Path) -> Path:
    """Parse `gitdir: ...` target from a worktree `.git` file."""
    first_line = git_file_path.read_text(encoding="utf-8").splitlines()[0].strip()
    prefix = "gitdir: "
    if not first_line.startswith(prefix):
        raise RuntimeError(f"Unsupported .git file format at {git_file_path}")
    return Path(first_line[len(prefix) :].strip())


def _resolve_true_git_dir(git_repo_path: Path) -> Path:
    """Resolve the true git common directory using git itself."""
    proc = _run_checked(
        ["git", "-C", str(git_repo_path), "rev-parse", "--git-common-dir"],
        capture_output=True,
    )
    git_common_dir = Path(proc.stdout.strip())
    if git_common_dir.is_absolute():
        return git_common_dir.resolve()
    return (git_repo_path / git_common_dir).resolve()


def _common_ancestor(path1: Path, path2: Path) -> Path:
    """Find the common ancestor path for two locations."""
    return Path(os.path.commonpath([str(path1), str(path2)]))


def _run_checked(
    cmd_args: Sequence[str], *, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run a command and raise if it fails."""
    return subprocess.run(
        list(cmd_args),
        check=True,
        capture_output=capture_output,
        text=True,
    )


def _active_image_build_plan(docker_images_root: Path) -> list[tuple[str, Path]]:
    """Return active image names and directories in dependency order."""
    if not docker_images_root.is_dir():
        raise RuntimeError(
            f"Docker image directory does not exist: {docker_images_root}"
        )
    plan: list[tuple[str, Path]] = []
    for image_dir in _sorted_active_image_dirs(docker_images_root):
        info = _load_image_info(image_dir / "image_info.json")
        image_name = info.get("image_name")
        if not isinstance(image_name, str) or not image_name:
            raise RuntimeError(f"Invalid image_name in {image_dir / 'image_info.json'}")
        plan.append((image_name, image_dir))
    return plan


def _stop_containers_using_volume(volume_name: str) -> None:
    """Stop and remove any containers that are using the given volume."""
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"volume={volume_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return
    for container_id in result.stdout.strip().splitlines():
        container_id = container_id.strip()
        if container_id:
            print(
                f"Removing container {container_id} (uses volume {volume_name}).",
                flush=True,
            )
            subprocess.run(
                ["docker", "rm", "-f", container_id],
                check=False,
                capture_output=True,
                text=True,
            )


def _remove_container_if_exists(container_name: str) -> None:
    """Remove a container if present, ignoring failures."""
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        check=False,
        capture_output=True,
        text=True,
    )


def _create_overlay_git_file_if_needed(
    mounting_args: MountingArgs, tempdir_path: Path
) -> Path | None:
    """Create temporary `.git` overlay when host gitdir path is absolute."""
    if (
        not mounting_args.git_file_uses_absolute_path
        or mounting_args.worktree_git_dir_relative_path is None
    ):
        return None
    overlay_git_file = tempdir_path / ".git-overlay"
    overlay_git_file.write_text(
        f"gitdir: {mounting_args.worktree_git_dir_relative_path.as_posix()}\n",
        encoding="utf-8",
    )
    return overlay_git_file


def _create_overlay_ci_script_if_needed(
    repo_root: Path, tempdir_path: Path
) -> Path | None:
    """Create LF-normalized ci-test overlay when CRLF is detected."""
    host_ci_script = repo_root / str(CI_SCRIPT_REL_PATH)
    try:
        script_content = host_ci_script.read_bytes()
    except OSError:
        return None
    if b"\r\n" not in script_content:
        return None
    normalized = script_content.replace(b"\r\n", b"\n")
    overlay = tempdir_path / "ci-test-overlay"
    overlay.write_bytes(normalized)
    return overlay


def _build_mount_args(
    *,
    mounting_args: MountingArgs,
    overlay_git_file: Path | None,
    overlay_ci_script: Path | None,
) -> list[str]:
    """Build `docker run` mount arguments."""
    args: list[str] = []
    args.extend(
        [
            "-v",
            f"{mounting_args.worktree.out_path}:{mounting_args.worktree.in_path}:ro",
        ]
    )
    if mounting_args.git_dir is not None:
        args.extend(
            [
                "-v",
                f"{mounting_args.git_dir.out_path}:{mounting_args.git_dir.in_path}:ro",
            ]
        )
    if overlay_git_file is not None:
        args.extend(
            [
                "-v",
                f"{overlay_git_file}:{mounting_args.worktree.in_path / '.git'}:ro",
            ]
        )
    if overlay_ci_script is not None:
        ci_script_target = mounting_args.worktree.in_path / CI_SCRIPT_REL_PATH
        args.extend(
            [
                "-v",
                f"{overlay_ci_script}:{ci_script_target}:ro",
            ]
        )
    return args


def _wait_for_inner_docker(container_name: str) -> None:
    """Wait until inner Docker daemon in the dind container is ready."""
    print("Waiting for inner Docker daemon to start...", flush=True)
    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", "-u", "dockeruser", container_name, "docker", "info"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            print("Inner Docker daemon is ready.", flush=True)
            return
        time.sleep(1.0)
    raise RuntimeError("Inner Docker daemon did not become ready in time.")


def _build_inner_images(container_name: str, repo_in_container: PurePosixPath) -> None:
    """Build active non-dind images inside the dind container."""
    docker_images_root_in_container = (
        repo_in_container
        / "am-common-lib/am-common-lib-src/test/resources/docker-images"
    )
    for image_name, image_dir in _active_image_build_plan(DOCKER_IMAGES_DIR):
        if image_name == "dind-dev":
            continue
        image_dir_in_container = docker_images_root_in_container / image_dir.name
        print(
            f"Building inner image: {image_name} ({image_dir_in_container})", flush=True
        )
        _run_checked(
            [
                "docker",
                "exec",
                "-u",
                "dockeruser",
                container_name,
                "docker",
                "build",
                "-t",
                image_name,
                str(image_dir_in_container),
            ]
        )


def _stream_ci_output(
    *,
    container_name: str,
    repo_in_container: PurePosixPath,
    log_path: Path,
    ci_commit: str,
) -> int:
    """Run CI script in container and tee output to host log.

    :param str container_name: Name of the running dind container.
    :param repo_in_container: Path to the repo worktree inside the container.
    :type repo_in_container: PurePosixPath
    :param Path log_path: Host path to write the CI log to.
    :param str ci_commit: Commit hash to check out inside the container.
    :return: The exit code from the CI script.
    :rtype: int
    """
    ci_script_in_container = repo_in_container / CI_SCRIPT_REL_PATH
    cmd_args = [
        "docker",
        "exec",
        "--env",
        "GIT_CONFIG_COUNT=1",
        "--env",
        "GIT_CONFIG_KEY_0=safe.directory",
        "--env",
        f"GIT_CONFIG_VALUE_0={repo_in_container}",
        "-u",
        "dockeruser",
        "-w",
        "/home/dockeruser",
        container_name,
        "bash",
        str(ci_script_in_container),
        ci_commit,
    ]
    print(f"Running: {shlex.join(cmd_args)}", flush=True)
    with subprocess.Popen(
        cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    ) as process:
        with log_path.open("w", encoding="utf-8", newline="\n") as log_file:
            _tee_process_output(process, log_file)
        return_code = process.wait()
    if return_code != 0:
        print(f"CI script exited with code {return_code}.", flush=True)
    return return_code


def _collect_and_bundle_results(
    *,
    container_name: str,
    repo_root: Path,
    ci_log_path: Path,
    tempdir_path: Path,
    run_timestamp: datetime,
    ci_passed: bool,
) -> Path:
    """Extract reports from the container and bundle with the CI log.

    :param str container_name: Name of the running dind container.
    :param Path repo_root: Repository root on the host.
    :param Path ci_log_path: Path to the CI log file on the host.
    :param Path tempdir_path: Scratch directory for intermediate files.
    :param run_timestamp: UTC timestamp captured right before the CI run.
    :type run_timestamp: datetime
    :param bool ci_passed: Whether the CI run completed successfully.
    :return: Path to the final reports tarball.
    :rtype: Path
    """
    inner_archive_path = _try_extract_reports_archive(container_name, tempdir_path)
    return _assemble_final_reports_bundle(
        repo_root=repo_root,
        inner_archive_path=inner_archive_path,
        ci_log_path=ci_log_path,
        run_timestamp=run_timestamp,
        ci_passed=ci_passed,
    )


def _sorted_active_image_dirs(docker_images_root: Path) -> list[Path]:
    """Return active image directories in dependency order."""
    graph = _collect_active_image_graph(docker_images_root)
    sorted_names = _topological_sort_image_names(
        graph.name_to_dir, graph.dependencies, graph.reverse_deps
    )
    return [graph.name_to_dir[name] for name in sorted_names]


def _load_image_info(image_info_path: Path) -> dict[str, object]:
    """Load a docker image metadata file."""
    with image_info_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected object in {image_info_path}")
    return data


def _tee_process_output(process: subprocess.Popen[str], log_file: TextIO) -> None:
    """Write subprocess output to stdout and a log file."""
    if process.stdout is None:
        raise RuntimeError("Expected process stdout to be available.")
    for line in iter(process.stdout.readline, ""):
        try:
            print(line, end="", flush=True)
        except UnicodeEncodeError:
            print(
                line.encode("ascii", errors="replace").decode("ascii"),
                end="",
                flush=True,
            )
        log_file.write(line)
        log_file.flush()


def _try_extract_reports_archive(
    container_name: str, tempdir_path: Path
) -> Path | None:
    """Try to copy the reports archive from the container.

    :param str container_name: Name of the running dind container.
    :param Path tempdir_path: Scratch directory for the extracted archive.
    :return: Path to the local copy, or ``None`` if unavailable.
    :rtype: Path | None
    """
    archive_path_in_container = _get_latest_reports_archive_path(container_name)
    if archive_path_in_container is None:
        return None
    local_path = tempdir_path / archive_path_in_container.name
    result = subprocess.run(
        [
            "docker",
            "cp",
            f"{container_name}:{archive_path_in_container}",
            str(local_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Could not copy reports archive: {result.stderr.strip()}", flush=True)
        return None
    return local_path


@dataclass(frozen=True)
class ParsedInnerArchiveName:
    """Parsed fields from the ci-test output archive filename."""

    tree_date: str
    tree_hash: str


def _assemble_final_reports_bundle(
    *,
    repo_root: Path,
    inner_archive_path: Path | None,
    ci_log_path: Path,
    run_timestamp: datetime,
    ci_passed: bool,
) -> Path:
    """Assemble final reports bundle under the repository `.ci-reports` directory.

    :param Path repo_root: Repository root on the host.
    :param inner_archive_path: Path to the inner reports archive, or ``None``.
    :type inner_archive_path: Path | None
    :param Path ci_log_path: Path to the CI log file on the host.
    :param run_timestamp: UTC timestamp captured right before the CI run.
    :type run_timestamp: datetime
    :param bool ci_passed: Whether the CI run completed successfully.
    :return: Path to the final reports tarball.
    :rtype: Path
    """
    ts = _format_timestamp(run_timestamp)
    reports_dir = repo_root / ".ci-reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    parsed = _try_parse_inner_archive_name(inner_archive_path)
    if parsed is not None:
        suffix = f"{parsed.tree_date}_{ts}_{parsed.tree_hash}"
    else:
        suffix = ts

    status = "PASSED" if ci_passed else "FAILED"
    final_archive_name = f"ci_reports_{status}_{suffix}.tar.gz"
    ci_log_name = f"ci_test_{suffix}.out"
    final_archive_path = reports_dir / final_archive_name

    with tempfile.TemporaryDirectory() as tempdir:
        tempdir_path = Path(tempdir)
        staging_dir = tempdir_path / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        if inner_archive_path is not None:
            with tarfile.open(inner_archive_path, "r:gz") as archive:
                try:
                    archive.extractall(path=staging_dir, filter="data")
                except TypeError:
                    archive.extractall(path=staging_dir)

        bundled_ci_log = staging_dir / ci_log_name
        bundled_ci_log.write_text(
            ci_log_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        with tarfile.open(final_archive_path, "w:gz") as out_archive:
            if (staging_dir / "reports").is_dir():
                out_archive.add(staging_dir / "reports", arcname="reports")
            out_archive.add(bundled_ci_log, arcname=ci_log_name)
    return final_archive_path


@dataclass(frozen=True)
class ImageGraph:
    """Container for active image graph metadata."""

    name_to_dir: dict[str, Path]
    dependencies: dict[str, set[str]]
    reverse_deps: dict[str, set[str]]


def _collect_active_image_graph(docker_images_root: Path) -> ImageGraph:
    """Collect active image nodes and dependency edges."""
    name_to_dir: dict[str, Path] = {}
    dependencies: dict[str, set[str]] = defaultdict(set)
    reverse_deps: dict[str, set[str]] = defaultdict(set)

    for image_info_file in sorted(docker_images_root.glob("*/image_info.json")):
        info = _load_image_info(image_info_file)
        image_name = _extract_active_image_name(info)
        if image_name is None:
            continue
        name_to_dir[image_name] = image_info_file.parent
        for dependency in _extract_dependencies(info):
            dependencies[image_name].add(dependency)
            reverse_deps[dependency].add(image_name)
    return ImageGraph(
        name_to_dir=name_to_dir,
        dependencies=dependencies,
        reverse_deps=reverse_deps,
    )


def _topological_sort_image_names(
    name_to_dir: dict[str, Path],
    dependencies: dict[str, set[str]],
    reverse_deps: dict[str, set[str]],
) -> list[str]:
    """Topologically sort image names by dependency graph."""
    indegree = {name: len(dependencies.get(name, set())) for name in name_to_dir}
    queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
    sorted_names: list[str] = []
    while queue:
        node = queue.popleft()
        sorted_names.append(node)
        for child in sorted(reverse_deps.get(node, set())):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(sorted_names) != len(name_to_dir):
        raise RuntimeError("Could not topologically sort docker images.")
    return sorted_names


def _get_latest_reports_archive_path(
    container_name: str,
) -> PurePosixPath | None:
    """Locate the newest reports archive path inside the container."""
    list_cmd = (
        "ls -1t "
        + shlex.quote(str(CONTAINER_REPO_CLONE_DIR))
        + "/reports_*.tar.gz 2>/dev/null | head -n1"
    )
    result = subprocess.run(
        ["docker", "exec", container_name, "sh", "-c", list_cmd],
        check=False,
        capture_output=True,
        text=True,
    )
    archive_path = result.stdout.strip()
    if result.returncode != 0 or not archive_path:
        print(f"No reports archive found in {CONTAINER_REPO_CLONE_DIR}.", flush=True)
        return None
    return PurePosixPath(archive_path)


def _format_timestamp(ts: datetime) -> str:
    """Format a UTC datetime as ``YYYYMMDD_HH_MM_SS_fff``."""
    ms = ts.microsecond // 1000
    return ts.strftime("%Y%m%d_%H_%M_%S") + f"_{ms:03d}"


def _try_parse_inner_archive_name(
    inner_archive_path: Path | None,
) -> ParsedInnerArchiveName | None:
    """Parse reports archive date/hash fields from the filename.

    :param inner_archive_path: Path to the inner archive, or ``None``.
    :type inner_archive_path: Path | None
    :return: Parsed fields, or ``None`` if parsing fails or path is ``None``.
    :rtype: ParsedInnerArchiveName | None
    """
    if inner_archive_path is None:
        return None
    archive_name = inner_archive_path.name
    if not archive_name.startswith("reports_") or not archive_name.endswith(".tar.gz"):
        return None
    suffix = archive_name[len("reports_") : -len(".tar.gz")]
    first_separator = suffix.find("_")
    if first_separator <= 0:
        return None
    tree_date = suffix[:first_separator]
    tree_hash = suffix[first_separator + 1 :]
    return ParsedInnerArchiveName(tree_date=tree_date, tree_hash=tree_hash)


def _extract_active_image_name(info: dict[str, object]) -> str | None:
    """Return image name for active image metadata."""
    if not info.get("active", False):
        return None
    image_name = info.get("image_name")
    if not isinstance(image_name, str) or not image_name:
        return None
    return image_name


def _extract_dependencies(info: dict[str, object]) -> list[str]:
    """Extract valid dependency names from image metadata."""
    raw_dependencies = info.get("depends_on", [])
    if not isinstance(raw_dependencies, list):
        return []
    deps: list[str] = []
    for dependency in raw_dependencies:
        if isinstance(dependency, str):
            deps.append(dependency)
    return deps


if __name__ == "__main__":
    main(tuple(sys.argv[1:]), sys.argv[0])
