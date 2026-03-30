"""Tests for :mod:`vdenv.mount_args`.

Covers normal clones, linked worktrees, and submodule checkouts. Integration tests mount
the calculated volumes into a throwaway Docker container and verify that git recognises
the repository.
"""

from __future__ import annotations

from collections.abc import Sequence
import os
from pathlib import Path
from pathlib import PurePosixPath
import subprocess
import tempfile

from assertpy import assert_that
from assertpy import soft_assertions
import pytest
from vdenv.mount_args import calculate_mount_args
from vdenv.mount_args import MountResult


_BASE: PurePosixPath = PurePosixPath("/home/dockeruser/src")

_COMMIT_MESSAGES: tuple[str, ...] = (
    "Initial commit",
    "Add data file",
    "Update readme",
)

_FILE_PROTO_ENV: dict[str, str] = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "protocol.file.allow",
    "GIT_CONFIG_VALUE_0": "always",
}


def _run_git(
    *args: str,
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = None
    if env is not None:
        run_env = {**os.environ, **env}
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
        env=run_env,
    )


def _create_bare_repo(
    base_dir: Path,
    name: str,
    branch: str,
) -> Path:
    """Create a bare repo at *base_dir/name.git* with three commits.

    Returns the path to the bare repository.
    """
    work = base_dir / f"{name}-work"
    work.mkdir()
    _run_git("init", "-b", branch, cwd=work)
    _run_git("config", "user.email", "test@test.local", cwd=work)
    _run_git("config", "user.name", "Test", cwd=work)

    readme = work / "readme.txt"
    readme.write_text(f"Hello from {name}\n", encoding="utf-8")
    _run_git("add", "readme.txt", cwd=work)
    _run_git("commit", "-m", _COMMIT_MESSAGES[0], cwd=work)

    data_dir = work / "data"
    data_dir.mkdir()
    (data_dir / "info.txt").write_text("data\n", encoding="utf-8")
    _run_git("add", "data/info.txt", cwd=work)
    _run_git("commit", "-m", _COMMIT_MESSAGES[1], cwd=work)

    readme.write_text(f"Updated hello from {name}\n", encoding="utf-8")
    _run_git("add", "readme.txt", cwd=work)
    _run_git("commit", "-m", _COMMIT_MESSAGES[2], cwd=work)

    bare = base_dir / f"{name}.git"
    _run_git("clone", "--bare", str(work), str(bare), cwd=base_dir)
    return bare


@pytest.fixture(scope="module")
def bare_repo_main(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Bare repo with default branch ``main`` and three commits."""
    base = tmp_path_factory.mktemp("bare-main")
    return _create_bare_repo(base, "repo-main", "main")


@pytest.fixture(scope="module")
def bare_repo_master(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Bare repo with default branch ``master`` and three commits."""
    base = tmp_path_factory.mktemp("bare-master")
    return _create_bare_repo(base, "repo-master", "master")


@pytest.fixture(scope="module")
def bare_repo_develop(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Bare repo with default branch ``develop`` and three commits."""
    base = tmp_path_factory.mktemp("bare-develop")
    return _create_bare_repo(base, "repo-develop", "develop")


def _docker_available() -> bool:
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return result.returncode == 0


def _docker_run_with_git(
    volume_args: Sequence[str],
    script: str,
    *,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run a one-shot Alpine container with git and execute *script*."""
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            *volume_args,
            "alpine:latest",
            "sh",
            "-c",
            (
                "apk add --no-cache git >/dev/null 2>&1 && "
                "git config --global safe.directory '*' && " + script
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


class TestCloneMountArgs:
    """Mount-arg calculation for a standard ``git clone``."""

    def test_git_dir_is_none(self, bare_repo_main: Path) -> None:
        """Normal clone has ``.git`` as a directory -- no separate git_dir."""
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "my-clone"
            _run_git("clone", f"file://{bare_repo_main}", str(clone), cwd=Path(td))
            result = calculate_mount_args(clone)

        with soft_assertions():
            assert_that(result.git_dir).described_as("git_dir").is_none()
            assert_that(result.overlay_git_content).described_as("overlay").is_none()

    def test_host_path(self, bare_repo_main: Path) -> None:
        """Worktree host path equals the clone directory."""
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "my-clone"
            _run_git("clone", f"file://{bare_repo_main}", str(clone), cwd=Path(td))
            result = calculate_mount_args(clone)

        assert_that(str(result.worktree.host_path)).described_as("host").is_equal_to(
            str(clone.resolve())
        )

    def test_container_path(self, bare_repo_main: Path) -> None:
        """Container repo path is ``base / clone_dir.name``."""
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "my-clone"
            _run_git("clone", f"file://{bare_repo_main}", str(clone), cwd=Path(td))
            result = calculate_mount_args(clone)

        assert_that(str(result.container_repo_path)).described_as(
            "container"
        ).is_equal_to(str(_BASE / "my-clone"))

    def test_volume_args_shape(self, bare_repo_main: Path) -> None:
        """Produces exactly one ``-v`` pair."""
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "my-clone"
            _run_git("clone", f"file://{bare_repo_main}", str(clone), cwd=Path(td))
            result = calculate_mount_args(clone)
            vol = result.volume_args()

        with soft_assertions():
            assert_that(vol).described_as("length").is_length(2)
            assert_that(vol[0]).described_as("flag").is_equal_to("-v")
            assert_that(vol[1]).described_as("bind").ends_with(":ro")


class TestWorktreeMountArgs:
    """Mount-arg calculation for a linked worktree."""

    @staticmethod
    def _setup_worktree(bare_repo: Path, base: Path) -> tuple[Path, MountResult]:
        clones = base / "clones"
        clones.mkdir()
        main_clone = clones / "main-clone"
        _run_git("clone", f"file://{bare_repo}", str(main_clone), cwd=clones)

        wt_dir = base / "worktrees" / "feature-x"
        wt_dir.parent.mkdir(parents=True)
        _run_git(
            "worktree",
            "add",
            str(wt_dir),
            "-b",
            "feature-x",
            cwd=main_clone,
        )
        result = calculate_mount_args(wt_dir)
        return wt_dir, result

    def test_git_dir_present(self, bare_repo_master: Path) -> None:
        """Worktree ``.git`` is a file -- git_dir must be populated."""
        with tempfile.TemporaryDirectory() as td:
            _, result = self._setup_worktree(bare_repo_master, Path(td))

        assert_that(result.git_dir).described_as("git_dir").is_not_none()

    def test_worktree_host_path(self, bare_repo_master: Path) -> None:
        """Worktree mount points at the worktree directory."""
        with tempfile.TemporaryDirectory() as td:
            wt_dir, result = self._setup_worktree(bare_repo_master, Path(td))

        assert_that(str(result.worktree.host_path)).described_as("host").is_equal_to(
            str(wt_dir.resolve())
        )

    def test_git_dir_host_path(self, bare_repo_master: Path) -> None:
        """git_dir host path points at the real .git common directory."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _, result = self._setup_worktree(bare_repo_master, base)
            main_git = (base / "clones" / "main-clone" / ".git").resolve()

        assert_that(str(result.git_dir.host_path)).described_as(  # type: ignore[union-attr]
            "git_dir"
        ).is_equal_to(str(main_git))

    def test_overlay_content(self, bare_repo_master: Path) -> None:
        """External worktrees need an overlay because gitdir is absolute."""
        with tempfile.TemporaryDirectory() as td:
            _, result = self._setup_worktree(bare_repo_master, Path(td))

        assert_that(result.overlay_git_content).described_as("overlay").is_not_none()
        assert_that(result.overlay_git_content).described_as("prefix").starts_with(
            "gitdir: "
        )

    def test_volume_args_count(self, bare_repo_master: Path) -> None:
        """With overlay, volume_args produces three ``-v`` pairs."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _, result = self._setup_worktree(bare_repo_master, base)
            overlay_file = base / "overlay-git"
            overlay_file.write_text(result.overlay_git_content or "", encoding="utf-8")
            vol = result.volume_args(overlay_git_file=overlay_file)

        assert_that(len(vol)).described_as("pairs").is_equal_to(6)

    def test_container_paths_under_base(self, bare_repo_master: Path) -> None:
        """Both container paths live under the configured base."""
        with tempfile.TemporaryDirectory() as td:
            _, result = self._setup_worktree(bare_repo_master, Path(td))

        base_str = str(_BASE)
        with soft_assertions():
            assert_that(str(result.worktree.container_path)).described_as(
                "worktree"
            ).starts_with(base_str)
            assert_that(
                str(result.git_dir.container_path)  # type: ignore[union-attr]
            ).described_as("git_dir").starts_with(base_str)


class TestSubmoduleMountArgs:
    """Mount-arg calculation for a git submodule."""

    @staticmethod
    def _setup_submodule(bare_repo: Path, base: Path) -> tuple[Path, MountResult]:
        super_dir = base / "superproject"
        super_dir.mkdir()
        _run_git("init", "-b", "main", cwd=super_dir)
        _run_git("config", "user.email", "test@test.local", cwd=super_dir)
        _run_git("config", "user.name", "Test", cwd=super_dir)

        (super_dir / "root.txt").write_text("super\n", encoding="utf-8")
        _run_git("add", "root.txt", cwd=super_dir)
        _run_git("commit", "-m", "super init", cwd=super_dir)

        _run_git(
            "submodule",
            "add",
            f"file://{bare_repo}",
            "libs/sub",
            cwd=super_dir,
            env=_FILE_PROTO_ENV,
        )
        _run_git("commit", "-m", "add submodule", cwd=super_dir)

        sub_path = super_dir / "libs" / "sub"
        result = calculate_mount_args(sub_path)
        return sub_path, result

    def test_git_dir_present(self, bare_repo_develop: Path) -> None:
        """Submodule ``.git`` is a file -- git_dir must be populated."""
        with tempfile.TemporaryDirectory() as td:
            _, result = self._setup_submodule(bare_repo_develop, Path(td))

        assert_that(result.git_dir).described_as("git_dir").is_not_none()

    def test_git_dir_points_into_parent_modules(self, bare_repo_develop: Path) -> None:
        """git_dir host path lives inside the parent's ``.git/modules``."""
        with tempfile.TemporaryDirectory() as td:
            _, result = self._setup_submodule(bare_repo_develop, Path(td))

        assert_that(
            str(result.git_dir.host_path)  # type: ignore[union-attr]
        ).described_as("modules").contains("modules")

    def test_container_paths_under_base(self, bare_repo_develop: Path) -> None:
        """Both container paths live under the configured base."""
        with tempfile.TemporaryDirectory() as td:
            _, result = self._setup_submodule(bare_repo_develop, Path(td))

        base_str = str(_BASE)
        with soft_assertions():
            assert_that(str(result.worktree.container_path)).described_as(
                "worktree"
            ).starts_with(base_str)
            assert_that(
                str(result.git_dir.container_path)  # type: ignore[union-attr]
            ).described_as("git_dir").starts_with(base_str)

    def test_volume_args_has_git_dir(self, bare_repo_develop: Path) -> None:
        """volume_args includes at least two ``-v`` pairs."""
        with tempfile.TemporaryDirectory() as td:
            _, result = self._setup_submodule(bare_repo_develop, Path(td))
            vol = result.volume_args()

        assert_that(len(vol)).described_as("args").is_greater_than_or_equal_to(4)


@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
class TestMountIntoContainer:
    """Mount a git repo into an Alpine container and verify git ops."""

    def test_clone(self, bare_repo_main: Path) -> None:
        """Normal clone: git recognises repo, files and log visible."""
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "my-clone"
            _run_git(
                "clone",
                f"file://{bare_repo_main}",
                str(clone),
                cwd=Path(td),
            )
            result = calculate_mount_args(clone)
            vol = result.volume_args()
            repo = result.container_repo_path

            script = (
                f"git -C {repo} rev-parse --show-toplevel && "
                f"cat {repo}/readme.txt && "
                f"git -C {repo} log --oneline"
            )
            proc = _docker_run_with_git(vol, script)

        lines = proc.stdout.strip().splitlines()
        with soft_assertions():
            assert_that(proc.returncode).described_as("rc").is_equal_to(0)
            assert_that(lines[0]).described_as("toplevel").is_equal_to(str(repo))
            assert_that(lines[1]).described_as("readme").contains("Updated hello")
            assert_that(len(lines)).described_as("lines").is_greater_than_or_equal_to(5)
            log_lines = lines[2:]
            for msg in _COMMIT_MESSAGES:
                assert_that([line for line in log_lines if msg in line]).described_as(
                    msg
                ).is_not_empty()

    def test_worktree(self, bare_repo_master: Path) -> None:
        """Worktree mount: git sees the correct toplevel and history."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            clones = base / "clones"
            clones.mkdir()
            main_clone = clones / "main-clone"
            _run_git(
                "clone",
                f"file://{bare_repo_master}",
                str(main_clone),
                cwd=clones,
            )

            wt_dir = base / "worktrees" / "feature-wt"
            wt_dir.parent.mkdir(parents=True)
            _run_git(
                "worktree",
                "add",
                str(wt_dir),
                "-b",
                "feature-wt",
                cwd=main_clone,
            )

            result = calculate_mount_args(wt_dir)
            overlay_path: Path | None = None
            if result.overlay_git_content is not None:
                overlay_path = base / ".git-overlay"
                overlay_path.write_text(result.overlay_git_content, encoding="utf-8")
            vol = result.volume_args(overlay_git_file=overlay_path)
            repo = result.container_repo_path

            script = (
                f"git -C {repo} rev-parse --show-toplevel && "
                f"cat {repo}/readme.txt && "
                f"git -C {repo} log --oneline"
            )
            proc = _docker_run_with_git(vol, script)

        lines = proc.stdout.strip().splitlines()
        with soft_assertions():
            assert_that(proc.returncode).described_as("rc").is_equal_to(0)
            assert_that(lines[0]).described_as("toplevel").is_equal_to(str(repo))
            assert_that(lines[1]).described_as("readme").contains("hello")
            log_lines = lines[2:]
            for msg in _COMMIT_MESSAGES:
                assert_that([line for line in log_lines if msg in line]).described_as(
                    msg
                ).is_not_empty()

    def test_submodule(self, bare_repo_develop: Path) -> None:
        """Submodule mount: git sees the submodule as a proper repo."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            super_dir = base / "superproject"
            super_dir.mkdir()
            _run_git("init", "-b", "main", cwd=super_dir)
            _run_git("config", "user.email", "test@test.local", cwd=super_dir)
            _run_git("config", "user.name", "Test", cwd=super_dir)
            (super_dir / "root.txt").write_text("super\n", encoding="utf-8")
            _run_git("add", "root.txt", cwd=super_dir)
            _run_git("commit", "-m", "super init", cwd=super_dir)
            _run_git(
                "submodule",
                "add",
                f"file://{bare_repo_develop}",
                "libs/sub",
                cwd=super_dir,
                env=_FILE_PROTO_ENV,
            )
            _run_git("commit", "-m", "add submodule", cwd=super_dir)

            sub_path = super_dir / "libs" / "sub"
            result = calculate_mount_args(sub_path)
            overlay_path: Path | None = None
            if result.overlay_git_content is not None:
                overlay_path = base / ".git-overlay"
                overlay_path.write_text(result.overlay_git_content, encoding="utf-8")
            vol = result.volume_args(overlay_git_file=overlay_path)
            repo = result.container_repo_path

            script = (
                f"git -C {repo} rev-parse --show-toplevel && "
                f"cat {repo}/readme.txt && "
                f"git -C {repo} log --oneline"
            )
            proc = _docker_run_with_git(vol, script)

        lines = proc.stdout.strip().splitlines()
        with soft_assertions():
            assert_that(proc.returncode).described_as("rc").is_equal_to(0)
            assert_that(lines[0]).described_as("toplevel").is_equal_to(str(repo))
            assert_that(lines[1]).described_as("readme").contains("hello")
            log_lines = lines[2:]
            for msg in _COMMIT_MESSAGES:
                assert_that([line for line in log_lines if msg in line]).described_as(
                    msg
                ).is_not_empty()
