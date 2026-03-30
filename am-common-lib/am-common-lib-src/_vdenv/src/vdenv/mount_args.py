"""Calculate Docker volume-mount arguments for binding a git repo into a container.

WARNING: Tentative! Unreviewed.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from pathlib import PurePosixPath
import subprocess
from typing import Final


DEFAULT_CONTAINER_BASE: Final[PurePosixPath] = PurePosixPath("/home/dockeruser/src")


@dataclass(frozen=True)
class MountPath:
    """A host-to-container path mapping."""

    host_path: Path
    container_path: PurePosixPath


@dataclass(frozen=True)
class MountResult:
    """Calculated mounting information for a git repository.

    :param worktree: Worktree host and container paths.
    :type worktree: MountPath
    :param git_dir: Git-data directory paths, or ``None`` for normal clones.
    :type git_dir: MountPath | None
    :param overlay_git_content: Replacement ``.git`` file body with a
        relative ``gitdir:`` line, or ``None`` when no overlay is needed.
    :type overlay_git_content: str | None
    """

    worktree: MountPath
    git_dir: MountPath | None
    overlay_git_content: str | None

    @property
    def container_repo_path(self) -> PurePosixPath:
        """Absolute path to the repo worktree inside the container."""
        return self.worktree.container_path

    def volume_args(
        self,
        *,
        read_only: bool = True,
        overlay_git_file: Path | None = None,
    ) -> tuple[str, ...]:
        """Produce ``-v`` flags suitable for ``docker run``.

        :param bool read_only: Append ``:ro`` to each bind-mount.
        :param overlay_git_file: Host path to a temporary ``.git`` overlay
            file.  Required when :attr:`overlay_git_content` is not ``None``.
        :type overlay_git_file: Path | None
        :return: Tuple of strings ready to be spliced into a command list.
        :rtype: tuple[str, ...]
        """
        suffix = ":ro" if read_only else ""
        args: list[str] = [
            "-v",
            (f"{self.worktree.host_path}:{self.worktree.container_path}{suffix}"),
        ]
        if self.git_dir is not None:
            args.extend(
                [
                    "-v",
                    (f"{self.git_dir.host_path}:{self.git_dir.container_path}{suffix}"),
                ]
            )
        if overlay_git_file is not None:
            args.extend(
                [
                    "-v",
                    (
                        f"{overlay_git_file}"
                        f":{self.worktree.container_path / '.git'}{suffix}"
                    ),
                ]
            )
        return tuple(args)


def calculate_mount_args(
    repo_path: str | os.PathLike[str],
    container_base_path: PurePosixPath = DEFAULT_CONTAINER_BASE,
) -> MountResult:
    """Calculate Docker bind-mount arguments for *repo_path*.

    :param repo_path: Host path to a git worktree root.
    :type repo_path: str | os.PathLike[str]
    :param container_base_path: Base directory inside the container under which mounts
        are placed.
    :type container_base_path: PurePosixPath
    :return: Mount paths and optional overlay metadata.
    :rtype: MountResult
    :raises FileNotFoundError: If *repo_path* has no ``.git`` entry.
    """
    repo = Path(repo_path).expanduser().resolve(strict=True)
    git_entry = repo / ".git"

    if not git_entry.exists():
        raise FileNotFoundError(f"No .git directory or file found at {git_entry}")

    if git_entry.is_dir():
        return MountResult(
            worktree=MountPath(repo, container_base_path / repo.name),
            git_dir=None,
            overlay_git_content=None,
        )

    git_file_target = _parse_git_file_target(git_entry)
    uses_absolute = git_file_target.is_absolute()
    true_git_dir = _resolve_true_git_dir(repo)
    ancestor = _common_ancestor(repo, true_git_dir)

    worktree_container = container_base_path / PurePosixPath(
        *repo.relative_to(ancestor).parts
    )
    git_dir_container = container_base_path / PurePosixPath(
        *true_git_dir.relative_to(ancestor).parts
    )
    overlay: str | None = None
    if uses_absolute:
        rel = PurePosixPath(*Path(os.path.relpath(true_git_dir, repo)).parts)
        overlay = f"gitdir: {rel}\n"

    return MountResult(
        worktree=MountPath(repo, worktree_container),
        git_dir=MountPath(true_git_dir, git_dir_container),
        overlay_git_content=overlay,
    )


def _parse_git_file_target(git_file: Path) -> Path:
    """Read ``gitdir: <path>`` from a ``.git`` file.

    :param Path git_file: Path to the ``.git`` file.
    :return: The target path extracted from the ``gitdir:`` line.
    :rtype: Path
    :raises ValueError: If the file does not start with ``gitdir:``.
    """
    first_line = git_file.read_text(encoding="utf-8").splitlines()[0].strip()
    prefix = "gitdir: "
    if not first_line.startswith(prefix):
        raise ValueError(f"Unexpected format in {git_file}: {first_line!r}")
    return Path(first_line[len(prefix) :].strip())


def _resolve_true_git_dir(repo_path: Path) -> Path:
    """Resolve the true git common directory via ``git rev-parse``.

    :param Path repo_path: Path to the git worktree.
    :return: Resolved absolute path to the git common directory.
    :rtype: Path
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    git_common_dir = Path(proc.stdout.strip())
    if git_common_dir.is_absolute():
        return git_common_dir.resolve()
    return (repo_path / git_common_dir).resolve()


def _common_ancestor(path_a: Path, path_b: Path) -> Path:
    """Return the deepest common ancestor of two paths.

    :param Path path_a: First path.
    :param Path path_b: Second path.
    :return: The deepest directory that is a prefix of both paths.
    :rtype: Path
    """
    return Path(os.path.commonpath([str(path_a), str(path_b)]))
