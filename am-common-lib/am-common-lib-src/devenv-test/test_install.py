from collections.abc import Generator
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from functools import lru_cache
import hashlib
import os
from pathlib import Path
from pathlib import PurePath
from pathlib import PurePosixPath
import shlex
import subprocess
from subprocess import CompletedProcess
import tempfile

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from am_common_lib import resource_utils
from am_common_lib.docker_util import ImageNames
from am_common_lib.docker_util.docker_runner import DockerRunner
from am_common_lib.docker_util.docker_runner import DockerRunnerUserView


@dataclass(frozen=True)
class ViewAndCheckedOutRepo:
    user_view: DockerRunnerUserView
    checked_out_repo_path: PurePosixPath


INSTALLABLE_FUNCTIONS: list[str] = ["ga", "gb", "gc", "gd", "gco", "gl", "gst"]
INSTALLABLE_ALIASES: list[str] = []
INSTALLABLE_EXECUTABLES: list[str] = ["cli-echo", "cli-echo-all", "gtl", "dedupe-path"]


def test_config() -> None:
    # A dummy test to ensure the relative paths are correct for the remaining
    txt = resource_utils.read_resource_text("devenv.scripts", "cli_echo.py")
    assert_that(len(txt)).is_greater_than(0)


def test_idempotency(
    initialized_container: ViewAndCheckedOutRepo,
) -> None:
    user_view = initialized_container.user_view
    container_tgt_file = "/home/basicuser/.bashrc"
    _run_install(initialized_container, container_tgt_file)
    # TODO: It should not be necessary to run this two more times.
    _run_install(initialized_container, container_tgt_file)
    _run_install(initialized_container, container_tgt_file)
    init_sha256 = hashlib.sha256(user_view.read_file(container_tgt_file)).hexdigest()
    _run_install(initialized_container, container_tgt_file)
    final_sha256 = hashlib.sha256(user_view.read_file(container_tgt_file)).hexdigest()
    assert_that(final_sha256).is_equal_to(init_sha256)


def test_symbols_do_not_collide_with_existing(
    _initialized_container_ro: ViewAndCheckedOutRepo,
) -> None:
    user_view = _initialized_container_ro.user_view
    orig_executables = set(_get_executables_in_path(user_view))
    orig_aliases = set(_get_aliases_in_session(user_view))
    orig_functions = set(_get_functions_in_session(user_view))

    with soft_assertions():
        assert_that(
            [x for x in INSTALLABLE_EXECUTABLES if x in orig_executables]
        ).described_as("shadows existing executable").is_empty()
        assert_that(
            [x for x in INSTALLABLE_FUNCTIONS if x in orig_functions]
        ).described_as("shadows existing function").is_empty()
        assert_that([x for x in INSTALLABLE_ALIASES if x in orig_aliases]).described_as(
            "shadows existing aliases"
        ).is_empty()


def test_installed_symbols_are_accounted_for(
    initialized_container: ViewAndCheckedOutRepo,
) -> None:
    user_view = initialized_container.user_view
    orig_executables = set(_get_executables_in_path(user_view))
    orig_aliases = set(_get_aliases_in_session(user_view))
    orig_functions = set(_get_functions_in_session(user_view))

    container_tgt_file = "/home/basicuser/.bashrc"
    _run_install(initialized_container, container_tgt_file)
    final_new_executables = [
        x for x in _get_executables_in_path(user_view) if x not in orig_executables
    ]
    final_new_aliases = [
        x for x in _get_aliases_in_session(user_view) if x not in orig_aliases
    ]
    final_new_functions = [
        x for x in _get_functions_in_session(user_view) if x not in orig_functions
    ]
    with soft_assertions():
        assert_that(
            [x for x in final_new_executables if x not in set(INSTALLABLE_EXECUTABLES)]
        ).described_as(
            "set of executables not accounted for should be empty"
        ).is_empty()
        assert_that(
            [x for x in final_new_aliases if x not in set(INSTALLABLE_ALIASES)]
        ).described_as("set of aliases not accounted for should be empty").is_empty()
        assert_that(
            [x for x in final_new_functions if x not in set(INSTALLABLE_FUNCTIONS)]
        ).described_as("set of functions not accounted for should be empty").is_empty()


def test_intended_symbols_are_installed(
    initialized_container: ViewAndCheckedOutRepo,
) -> None:
    user_view = initialized_container.user_view
    orig_executables = set(_get_executables_in_path(user_view))
    orig_aliases = set(_get_aliases_in_session(user_view))
    orig_functions = set(_get_functions_in_session(user_view))
    container_tgt_file = "/home/basicuser/.bashrc"
    _run_install(initialized_container, container_tgt_file)
    final_new_executables = {
        x for x in _get_executables_in_path(user_view) if x not in orig_executables
    }
    final_new_aliases = {
        x for x in _get_aliases_in_session(user_view) if x not in orig_aliases
    }
    final_new_functions = {
        x for x in _get_functions_in_session(user_view) if x not in orig_functions
    }

    assert_that(
        [x for x in INSTALLABLE_EXECUTABLES if x not in final_new_executables]
    ).described_as(
        "all executables intended to be installed should be found after installation"
    ).is_empty()
    assert_that(
        [x for x in INSTALLABLE_FUNCTIONS if x not in final_new_functions]
    ).described_as(
        "all functions intended to be installed should be found after installation"
    ).is_empty()
    assert_that(
        [x for x in INSTALLABLE_ALIASES if x not in final_new_aliases]
    ).described_as(
        "all aliases intended to be installed should be found after installation"
    ).is_empty()


def test_full_installation(
    initialized_container: ViewAndCheckedOutRepo,
) -> None:
    user_view = initialized_container.user_view
    installed_shortcuts = (
        INSTALLABLE_ALIASES + INSTALLABLE_EXECUTABLES + INSTALLABLE_FUNCTIONS
    )

    def do_cmd_assertions(assert_equals: bool) -> None:
        for shortcut in installed_shortcuts:
            cmd = [
                "bash",
                "-ic",
                shlex.join(("command", "-V", shortcut)),
            ]
            r = user_view.run(cmd, text=True)
            if assert_equals:
                assert_that(r.returncode).described_as(shortcut).is_equal_to(0)
            else:
                assert_that(r.returncode).described_as(shortcut).is_not_equal_to(0)

    do_cmd_assertions(False)
    container_tgt_file = "/home/basicuser/.bashrc"
    _run_install(initialized_container, container_tgt_file)
    do_cmd_assertions(True)


@pytest.mark.parametrize("shortcut", INSTALLABLE_EXECUTABLES)
def test_sym_links(installed_container_ro: DockerRunnerUserView, shortcut: str) -> None:
    # Assert that the symlink is not broken, that the target is executable.
    res = installed_container_ro.run(
        ["bash", "-ic", f"{_inspect_symlink_src()}\ninspect_symlink {shortcut}"],
        exec_args=["-t"],
        text=True,
    )
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        assert_that(res.stdout).described_as("stdout").is_equal_to("")
        assert_that(res.stderr).described_as("stderr").is_equal_to("")


def _get_executables_in_path(user_view: DockerRunnerUserView) -> Sequence[str]:
    result: CompletedProcess[str] = user_view.run(
        [
            "bash",
            "-ic",
            _cached_read_resource_text("resources", "get_command_list.sh"),
        ],
        exec_args=["-t"],
        text=True,
    )
    return result.stdout.split("\n")


def _get_aliases_in_session(user_view: DockerRunnerUserView) -> Sequence[str]:
    result: CompletedProcess[str] = user_view.run(
        [
            "bash",
            "-ic",
            _cached_read_resource_text("resources", "get_aliases.sh"),
        ],
        exec_args=["-t"],
        text=True,
    )
    return result.stdout.split("\n")


def _get_functions_in_session(user_view: DockerRunnerUserView) -> Sequence[str]:
    result: CompletedProcess[str] = user_view.run(
        [
            "bash",
            "-ic",
            _cached_read_resource_text("resources", "get_shell_functions.sh"),
        ],
        exec_args=["-t"],
        text=True,
    )
    return result.stdout.split("\n")


@lru_cache(maxsize=10)
def _cached_read_resource_text(package: str, resource: str) -> str:
    return resource_utils.read_resource_text(package, resource)


@cache
def _commit_to_checkout() -> tuple[str, Path]:
    repo_path = _get_toplevel(__file__)
    return _commit_current_working_tree(str(repo_path)), repo_path


@pytest.fixture(scope="function")
def initialized_container() -> Generator[ViewAndCheckedOutRepo]:
    yield from _construct_initialized_container()


@pytest.fixture(scope="module")
def installed_container_ro(
    _initialized_container_ro: ViewAndCheckedOutRepo,
) -> DockerRunnerUserView:
    _run_install(_initialized_container_ro, "/home/basicuser/.bashrc")
    return _initialized_container_ro.user_view


@pytest.fixture(scope="module")
def _initialized_container_ro() -> Generator[ViewAndCheckedOutRepo]:
    yield from _construct_initialized_container()


def _run_install(
    view_and_checked_out_repo: ViewAndCheckedOutRepo, container_tgt_file: str
) -> None:
    view_and_checked_out_repo.checked_out_repo_path / "devenv" / "install.py"
    r = view_and_checked_out_repo.user_view.run(
        [
            "python3",
            (
                view_and_checked_out_repo.checked_out_repo_path
                / "devenv"
                / "install.py"
            ).as_posix(),
            "--rc-file",
            container_tgt_file,
        ],
        text=True,
    )

    with soft_assertions():
        assert_that(r.returncode).described_as("returncode").is_equal_to(0)
        assert_that(r.stdout).described_as("stdout").is_not_empty()
        assert_that(r.stderr).described_as("stderr").is_empty()


@cache
def _inspect_symlink_src() -> str:
    return resource_utils.read_resource_text("resources", "inspect_symlink.sh")


@cache
def _get_toplevel(for_path: str | os.PathLike[str]) -> Path:
    """Get the git top-level (or root) for the file or folder 'for_path'."""
    r: CompletedProcess[str] = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(os.path.dirname(for_path)),
        capture_output=True,
        check=True,
        text=True,
    )

    return Path(r.stdout.strip())


def _commit_current_working_tree(git_path: str) -> str:
    """Returns a *commit* that is guaranteed to point to a tree identical to the current
    working tree, without checking it out or disturbing the state of the working tree or
    index."""
    porcelain_status = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        cwd=git_path,
        text=True,
        capture_output=True,
    )

    if porcelain_status.returncode == 128:
        raise RuntimeError(
            f"fatal: not a git repository. Command response: {porcelain_status}"
        )
    if not porcelain_status.stdout.strip():
        # Working tree is clean, so do not create a new commit
        print(f"Stdout consists of {porcelain_status.stdout}")
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_path,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_index_path = os.path.join(tmp_dir, "git-index")
        open(tmp_index_path, "w").close()
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = tmp_index_path

        # Seed the index from HEAD if it exists
        head_exists = (
            subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                check=False,
                cwd=git_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        if head_exists:
            subprocess.run(
                ["git", "read-tree", "HEAD"],
                cwd=git_path,
                env=env,
                capture_output=True,
                check=True,
            )

        # Stage everything (tracked changes, new/untracked files, deletions)
        subprocess.run(
            ["git", "add", "--all"],
            cwd=git_path,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

        # Write the tree and capture its ID
        tree_id = subprocess.run(
            ["git", "write-tree"],
            cwd=git_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            text=True,
        ).stdout.strip()

        # Create a commit object pointing at that tree
        commit_cmd = [
            "git",
            "commit-tree",
            tree_id,
            "-m",
            "Temporary commit for working tree",
        ]
        if head_exists:
            commit_cmd.extend(["-p", "HEAD"])

        return subprocess.run(
            commit_cmd,
            cwd=git_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            text=True,
        ).stdout.strip()


def _is_working_tree_clean(git_path: str) -> bool:
    porcelain_status = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        cwd=git_path,
        text=True,
        capture_output=True,
    )

    if porcelain_status.returncode == 128:
        raise RuntimeError(
            f"fatal: not a git repository. Command response: {porcelain_status}"
        )

    return porcelain_status.stdout == ""


def _construct_initialized_container() -> Generator[ViewAndCheckedOutRepo]:
    """Returns a container loaded with a copy of the repository, checked out to the
    right commit."""
    commit_id, repo_path = _commit_to_checkout()
    extra_args, container_repo_path = _calculate_mount_args(
        _get_toplevel(__file__), PurePosixPath("/", "home", "basicuser", "git_src")
    )
    with DockerRunner(ImageNames.PYTHON_DEV, run_args=extra_args) as runner:
        yield _load(
            runner,
            commit_id,
            container_repo_path,
            PurePath("/", "home", "basicuser", "dev-bootstrap").as_posix(),
        )


def _calculate_mount_args(
    repo_to_mount: str | os.PathLike[str], container_base_path: PurePosixPath
) -> tuple[Sequence[str], PurePosixPath]:
    """
    Returns:
      - extra_args: Docker -v args to mount the minimal host dir (read-only)
      - container_repo_path: absolute path INSIDE the container where the repo lives
    """
    repo = Path(repo_to_mount).expanduser().resolve(strict=True)

    host_root = _get_root_to_mount(repo)

    mount_point = container_base_path / host_root.name
    extra_args = ("-v", f"{str(host_root)}:{str(mount_point)}:ro")

    rel = repo.relative_to(host_root)

    return extra_args, mount_point.joinpath(*rel.parts)


def _load(
    runner: DockerRunner,
    commit_id: str,
    container_repo_path: PurePosixPath,
    container_repo_tgt_path: str,
) -> ViewAndCheckedOutRepo:
    user_view = runner.use_as("basicuser")
    res = user_view.run(
        ["git", "config", "--global", "--add", "safe.directory", "*"], text=True
    )
    assert_that(res.returncode).is_equal_to(0)

    res = user_view.run(
        [
            "git",
            "clone",
            container_repo_path.as_uri(),
            container_repo_tgt_path,
        ],
        text=True,
    )
    assert_that(res.returncode).is_equal_to(0)

    user_view.chdir(container_repo_tgt_path)
    res = user_view.run(["git", "fetch", "origin", commit_id], text=True)
    assert_that(res.returncode).described_as("returncode").is_equal_to(0)
    res = user_view.run(["git", "checkout", commit_id], text=True)
    assert_that(res.returncode).described_as("returncode").is_equal_to(0)
    return ViewAndCheckedOutRepo(user_view, PurePosixPath(container_repo_tgt_path))


def _get_root_to_mount(repo_to_mount: str | os.PathLike[str]) -> Path:
    """Compute the minimal host directory that must be mounted so both the Git working
    tree and its metadata are accessible.

    Handles submodules (where .git is a file pointing elsewhere) by resolving that
    gitdir and returning the deepest common ancestor.
    """
    repo = Path(repo_to_mount).expanduser().resolve(strict=True)
    git_entry = repo / ".git"
    if not git_entry.exists():
        raise FileNotFoundError(f"No `.git` directory or file found at {git_entry}")

    # find the real .git directory
    if git_entry.is_dir():
        git_dir = git_entry.resolve(strict=True)
    else:
        # read "gitdir: <path>"
        first = git_entry.read_text(encoding="utf-8").splitlines()[0].strip()
        if not first.startswith("gitdir:"):
            raise ValueError(f"Unexpected format in {git_entry}: {first!r}")
        path_ref = first[len("gitdir:") :].strip()
        git_path = Path(path_ref)
        git_dir = (git_path if git_path.is_absolute() else (repo / git_path)).resolve(
            strict=True
        )

    # deepest common ancestor of repo and its git data dir
    try:
        common = os.path.commonpath([str(repo), str(git_dir)])
    except ValueError:
        # e.g. different drives on Windows
        raise ValueError(f"Cannot compute a common ancestor for {repo} and {git_dir}")

    return Path(common)
