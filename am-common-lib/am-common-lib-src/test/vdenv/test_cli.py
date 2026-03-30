"""Subprocess-based tests for the ``vdenv-mgmt`` CLI.

Every test invokes the CLI as ``uv run vdenv-mgmt ...`` rather than
importing the module directly, validating the full entry-point path.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Final

from assertpy import assert_that
from assertpy import soft_assertions


_FILE_PROTO_ENV: Final[dict[str, str]] = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "protocol.file.allow",
    "GIT_CONFIG_VALUE_0": "always",
}


def _run_cli(
    *args: str,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke ``vdenv-mgmt`` as a subprocess.

    :param args: CLI arguments.
    :param cwd: Working directory for the subprocess.
    :type cwd: str | Path | None
    :param env: Extra environment variables merged with ``os.environ``.
    :type env: dict[str, str] | None
    :return: Completed process result.
    :rtype: subprocess.CompletedProcess[str]
    """
    import os

    full_env: dict[str, str] | None = None
    if env is not None:
        full_env = {**os.environ, **env}
    return subprocess.run(
        ["uv", "run", "vdenv-mgmt", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=full_env,
        timeout=60,
    )


def _run_git(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    import os

    cmd = ["git"]
    if cwd is not None:
        cmd.extend(["-C", str(cwd)])
    cmd.extend(args)

    full_env: dict[str, str] | None = None
    if env is not None:
        full_env = {**os.environ, **env}
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        env=full_env,
        timeout=30,
    )


def _init_git_repo(path: Path, *, branch: str = "main") -> None:
    """Create a minimal git repository with one commit."""
    _run_git("init", "-b", branch, str(path))
    _run_git("config", "user.name", "Test User", cwd=path)
    _run_git("config", "user.email", "test@test.local", cwd=path)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _run_git("add", ".", cwd=path)
    _run_git("commit", "-m", "initial", cwd=path)


def _extract_v_args(tokens: list[str]) -> list[str]:
    """Extract the arguments that follow ``-v`` flags."""
    args: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "-v" and i + 1 < len(tokens):
            args.append(tokens[i + 1])
            i += 2
        else:
            i += 1
    return args


class TestInfoMode:
    """``--info`` prints computed names and exits cleanly."""

    def test_info_mode(self, tmp_path: Path) -> None:
        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)

        result = _run_cli(str(repo), "--info")

        with soft_assertions():
            assert_that(result.returncode).is_equal_to(0)
            assert_that(result.stdout).contains("Container name:")
            assert_that(result.stdout).contains("vdenv-ssh-myproject-")
            assert_that(result.stdout).contains("SSH port:")
            assert_that(result.stdout).contains("Docker volume:")
            assert_that(result.stdout).contains("uv cache vol:")
            assert_that(result.stdout).contains("Repo type:")
            assert_that(result.stdout).contains("A")

    def test_info_mode_with_suffix(self, tmp_path: Path) -> None:
        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)

        result = _run_cli(str(repo), "--info", "--suffix", "dev")

        with soft_assertions():
            assert_that(result.returncode).is_equal_to(0)
            assert_that(result.stdout).contains("vdenv-ssh-myproject-dev-")

    def test_info_deterministic(self, tmp_path: Path) -> None:
        """Two runs with the same path yield the same names/ports."""
        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)

        first = _run_cli(str(repo), "--info")
        second = _run_cli(str(repo), "--info")

        assert_that(first.stdout).is_equal_to(second.stdout)


class TestDryRunMode:
    """``--dry-run`` prints the ``docker run`` command without running it."""

    def test_dry_run_contains_docker_run(self, tmp_path: Path) -> None:
        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)

        result = _run_cli(str(repo), "--dry-run")

        with soft_assertions():
            assert_that(result.returncode).is_equal_to(0)
            assert_that(result.stdout).contains("docker run")
            assert_that(result.stdout).contains("--privileged")
            assert_that(result.stdout).contains("--restart")
            assert_that(result.stdout).contains("unless-stopped")
            assert_that(result.stdout).contains("vdenv-ssh:latest")

    def test_dry_run_normal_clone_git_ro(self, tmp_path: Path) -> None:
        """For a normal clone, ``.git`` inside worktree is mounted ro."""
        import shlex

        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)

        result = _run_cli(str(repo), "--dry-run")
        assert_that(result.returncode).is_equal_to(0)

        tokens = shlex.split(result.stdout.strip())
        v_args = _extract_v_args(tokens)
        git_mounts = [a for a in v_args if ".git" in a and ".git" in a]
        with soft_assertions():
            assert_that(git_mounts).is_length(1)
            assert_that(git_mounts[0]).ends_with(":ro")

    def test_dry_run_normal_clone_rw_git(self, tmp_path: Path) -> None:
        """With ``--rw-git``, no ``:ro`` mount for ``.git``."""
        import shlex

        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)

        result = _run_cli(str(repo), "--dry-run", "--rw-git")
        assert_that(result.returncode).is_equal_to(0)

        tokens = shlex.split(result.stdout.strip())
        v_args = _extract_v_args(tokens)
        git_ro = [a for a in v_args if ".git" in a and a.endswith(":ro")]
        assert_that(git_ro).is_empty()

    def test_dry_run_custom_image(self, tmp_path: Path) -> None:
        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)

        result = _run_cli(str(repo), "--dry-run", "--image", "my-custom:1.0")

        with soft_assertions():
            assert_that(result.returncode).is_equal_to(0)
            assert_that(result.stdout).contains("my-custom:1.0")

    def test_dry_run_rw_git_no_ro_suffix(self, tmp_path: Path) -> None:
        """With ``--rw-git``, the ``.git`` dir mount has no ``:ro``."""
        import shlex

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        main_clone = workspace / "main-clone"
        main_clone.mkdir()
        _init_git_repo(main_clone)

        worktree_dir = workspace / "wt"
        _run_git(
            "worktree",
            "add",
            "-b",
            "feature",
            str(worktree_dir),
            cwd=main_clone,
        )

        result = _run_cli(str(worktree_dir), "--dry-run", "--rw-git")
        assert_that(result.returncode).is_equal_to(0)

        tokens = shlex.split(result.stdout.strip())
        v_args = _extract_v_args(tokens)
        git_dir_mounts = [a for a in v_args if "main-clone" in a and ".git" in a]
        with soft_assertions():
            assert_that(git_dir_mounts).is_not_empty()
            for mount in git_dir_mounts:
                assert_that(mount.endswith(":ro")).is_false()

    def test_dry_run_default_git_ro(self, tmp_path: Path) -> None:
        """Without ``--rw-git``, ``.git`` dir mount has ``:ro`` suffix."""
        import shlex

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        main_clone = workspace / "main-clone"
        main_clone.mkdir()
        _init_git_repo(main_clone)

        worktree_dir = workspace / "wt"
        _run_git(
            "worktree",
            "add",
            "-b",
            "feature",
            str(worktree_dir),
            cwd=main_clone,
        )

        result = _run_cli(str(worktree_dir), "--dry-run")
        assert_that(result.returncode).is_equal_to(0)

        tokens = shlex.split(result.stdout.strip())
        v_args = _extract_v_args(tokens)
        git_dir_mounts = [a for a in v_args if "main-clone" in a and ".git" in a]
        with soft_assertions():
            assert_that(git_dir_mounts).is_not_empty()
            for mount in git_dir_mounts:
                assert_that(mount).ends_with(":ro")

    def test_dry_run_extra_volume(self, tmp_path: Path) -> None:
        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)

        result = _run_cli(
            str(repo),
            "--dry-run",
            "--extra-volume",
            "/host/a:/ctr/a",
            "--extra-volume",
            "/host/b:/ctr/b",
        )

        with soft_assertions():
            assert_that(result.returncode).is_equal_to(0)
            assert_that(result.stdout).contains("/host/a:/ctr/a")
            assert_that(result.stdout).contains("/host/b:/ctr/b")


class TestNonGitRepo:
    """Type C (non-git) handling."""

    def test_non_git_repo_rejected(self, tmp_path: Path) -> None:
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = _run_cli(str(plain_dir), "--info")

        with soft_assertions():
            assert_that(result.returncode).is_not_equal_to(0)
            assert_that(result.stderr).contains("--allow-non-git-repo")

    def test_non_git_repo_allowed_dry_run(self, tmp_path: Path) -> None:
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = _run_cli(str(plain_dir), "--allow-non-git-repo", "--dry-run")

        with soft_assertions():
            assert_that(result.returncode).is_equal_to(0)
            assert_that(result.stdout).contains("docker run")

    def test_non_git_repo_info(self, tmp_path: Path) -> None:
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = _run_cli(str(plain_dir), "--allow-non-git-repo", "--info")

        with soft_assertions():
            assert_that(result.returncode).is_equal_to(0)
            assert_that(result.stdout).contains("Repo type:")
            assert_that(result.stdout).contains("C")


class TestTypeBDryRun:
    """Type B (subdirectory of a git repo) handling."""

    def test_type_b_plain_mount(self, tmp_path: Path) -> None:
        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)
        sub = repo / "subdir"
        sub.mkdir()

        result = _run_cli(str(sub), "--dry-run")

        with soft_assertions():
            assert_that(result.returncode).is_equal_to(0)
            assert_that(result.stdout).contains("docker run")
            assert_that(result.stdout).contains("subdir")

    def test_type_b_info(self, tmp_path: Path) -> None:
        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)
        sub = repo / "subdir"
        sub.mkdir()

        result = _run_cli(str(sub), "--info")

        with soft_assertions():
            assert_that(result.returncode).is_equal_to(0)
            assert_that(result.stdout).contains("Repo type:")
            assert_that(result.stdout).contains("B")

    def test_type_b_rw_git_rejected(self, tmp_path: Path) -> None:
        repo = tmp_path / "myproject"
        repo.mkdir()
        _init_git_repo(repo)
        sub = repo / "subdir"
        sub.mkdir()

        result = _run_cli(str(sub), "--rw-git", "--dry-run")

        with soft_assertions():
            assert_that(result.returncode).is_not_equal_to(0)
            assert_that(result.stderr).contains("--rw-git")


def _remove_ssh_config_block(container_name: str) -> None:
    """Remove the vdenv SSH config block for a container from ~/.ssh/config."""
    import re

    alias = f"vdenv-{container_name}"
    ssh_config = Path.home() / ".ssh" / "config"
    if not ssh_config.exists():
        return
    content = ssh_config.read_text(encoding="utf-8")
    begin = f"# BEGIN vdenv: {alias}"
    end = f"# END vdenv: {alias}"
    pattern = re.escape(begin) + r".*?" + re.escape(end) + r"\n?"
    cleaned = re.sub(pattern, "", content, flags=re.DOTALL)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    ssh_config.write_text(cleaned, encoding="utf-8")


class TestDockerIntegration:
    """Tests that actually create containers.

    Uses the ``vdenv_ssh_image`` fixture from conftest so the image tag
    is configurable via ``--vdenv-ssh`` and the class is skipped when
    the image is absent.
    """

    def test_create_and_remove_container(
        self, tmp_path: Path, vdenv_ssh_image: str
    ) -> None:
        repo = tmp_path / "clitest"
        repo.mkdir()
        _init_git_repo(repo)

        result = _run_cli(str(repo), "--force", "--image", vdenv_ssh_image)
        assert_that(result.returncode).is_equal_to(0)

        info_result = _run_cli(str(repo), "--info")
        container_name = ""
        for line in info_result.stdout.splitlines():
            if line.strip().startswith("Container name:"):
                container_name = line.split(":", 1)[1].strip()
                break

        try:
            inspect = subprocess.run(
                ["docker", "container", "inspect", container_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            assert_that(inspect.returncode).is_equal_to(0)
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            _remove_ssh_config_block(container_name)

    def test_sync_git_config(self, tmp_path: Path, vdenv_ssh_image: str) -> None:
        repo = tmp_path / "synctest"
        repo.mkdir()
        _init_git_repo(repo)

        create = _run_cli(str(repo), "--force", "--image", vdenv_ssh_image)
        assert_that(create.returncode).is_equal_to(0)

        info_result = _run_cli(str(repo), "--info")
        container_name = ""
        for line in info_result.stdout.splitlines():
            if line.strip().startswith("Container name:"):
                container_name = line.split(":", 1)[1].strip()
                break

        try:
            sync = _run_cli(str(repo), "--sync")

            with soft_assertions():
                assert_that(sync.returncode).is_equal_to(0)
                assert_that(sync.stdout).contains("Git config synced")

            config_val = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-u",
                    "dockeruser",
                    container_name,
                    "git",
                    "config",
                    "--global",
                    "--get-all",
                    "safe.directory",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            assert_that(config_val.stdout).contains("*")
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            _remove_ssh_config_block(container_name)

    def test_force_recreate(self, tmp_path: Path, vdenv_ssh_image: str) -> None:
        repo = tmp_path / "forcetest"
        repo.mkdir()
        _init_git_repo(repo)

        first = _run_cli(str(repo), "--force", "--image", vdenv_ssh_image)
        assert_that(first.returncode).is_equal_to(0)

        info_result = _run_cli(str(repo), "--info")
        container_name = ""
        for line in info_result.stdout.splitlines():
            if line.strip().startswith("Container name:"):
                container_name = line.split(":", 1)[1].strip()
                break

        try:
            second = _run_cli(str(repo), "--force", "--image", vdenv_ssh_image)
            assert_that(second.returncode).is_equal_to(0)

            inspect = subprocess.run(
                [
                    "docker",
                    "container",
                    "inspect",
                    "-f",
                    "{{.State.Running}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            assert_that(inspect.stdout.strip()).is_equal_to("true")
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            _remove_ssh_config_block(container_name)
