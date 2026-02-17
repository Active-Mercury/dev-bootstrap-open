"""Run Prettier via Docker for non-Python file formatting.

Locates the project root, changes to that directory, then runs
``npx prettier`` inside a Docker container.  Any extra CLI arguments are
forwarded to Prettier (e.g. ``--check`` instead of ``--write``).
"""

from collections.abc import Sequence
import os
import os.path
import shlex
import subprocess
import sys
from typing import Final


_CONTAINER_REPO: Final[str] = "/home/basicuser/prettier-formatter/git-repo"


def script_entry_point() -> None:
    """Console-script entry point that delegates to :func:`main`."""
    sys.exit(main(tuple(sys.argv[1:]), sys.argv[0], __name__))


def main(cmd_args: Sequence[str], prog_path: str, entry_name: str) -> int:
    """Run Prettier inside a Docker container.

    :param cmd_args: Extra arguments forwarded to Prettier.
    :type cmd_args: Sequence[str]
    :param str prog_path: The program path (i.e., sys.argv[0] or equivalent).
    :param str entry_name: The ``__name__`` of the calling module.
    :return: Exit code from the Docker/Prettier process.
    :rtype: int
    """
    project_root = _find_project_root()
    os.chdir(project_root)
    return _run_prettier(project_root, list(cmd_args))


def _find_project_root() -> str:
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isfile(os.path.join(cur, "pyproject.toml")) and os.path.isdir(
            os.path.join(cur, "am_common_lib")
        ):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    msg = "Could not locate project root (no pyproject.toml + am_common_lib found)"
    raise FileNotFoundError(msg)


def _run_prettier(project_root: str, extra_args: list[str]) -> int:
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{project_root}:{_CONTAINER_REPO}",
        "-w",
        f"{_CONTAINER_REPO}/.",
        "python-dev-loaded",
        "npx",
        "prettier",
        ".",
        "--write",
        *extra_args,
    ]
    print(f"Running: {shlex.join(cmd)}")
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    script_entry_point()
