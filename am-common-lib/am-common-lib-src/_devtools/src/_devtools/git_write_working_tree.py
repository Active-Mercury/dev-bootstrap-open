"""Compute or create a Git tree object from the working directory."""

from __future__ import annotations

import argparse
from argparse import ArgumentParser
from collections.abc import Sequence
import os
import os.path
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def script_entry_point() -> None:
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
    parser = _get_parser(os.path.basename(prog_path))
    parsed_args = parser.parse_args(cmd_args)

    tree_hash = compute_working_tree(parsed_args.ephemeral)
    print(tree_hash)
    return 0


def compute_working_tree(ephemeral: bool) -> str:
    """Compute the Git tree hash for the current working directory.

    :param bool ephemeral: When ``True``, use a temporary object database and do
        not store objects in the repository object database.
    :returns: The computed tree hash.
    :rtype: str
    """
    porcelain = _run_git(["status", "--porcelain", "--ignore-submodules=dirty"]).strip()
    if porcelain == "":
        return _run_git(["write-tree"]).strip()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        tmp_index_path = temp_dir_path / "tmp_index"
        tmp_index_path.touch()

        real_index = _run_git(["rev-parse", "--git-path", "index"]).strip()
        if os.path.isfile(real_index):
            shutil.copy2(real_index, tmp_index_path)

        base_env = os.environ.copy()
        env_with_index = {**base_env, "GIT_INDEX_FILE": str(tmp_index_path)}

        if not ephemeral:
            return _add_and_write_tree(env_with_index)

        gitdir = _run_git(["rev-parse", "--git-dir"]).strip()
        env_ephemeral = {
            **env_with_index,
            "GIT_OBJECT_DIRECTORY": temp_dir,
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.path.join(gitdir, "objects"),
        }
        return _add_and_write_tree(env_ephemeral)


def _get_parser(prog_name: str) -> ArgumentParser:
    parser = ArgumentParser(
        prog=prog_name,
        description=(
            "Compute the Git tree for the current working directory without "
            "modifying the index. By default, the tree object is written to "
            "the repository object database. With --ephemeral, the tree is "
            "computed using a temporary object database and is not stored; "
            "the printed hash may not be referenceable later."
        ),
        formatter_class=lambda prog: argparse.HelpFormatter(prog, width=80),
    )

    parser.add_argument(
        "-e",
        "--ephemeral",
        action="store_true",
        help=(
            "Compute the tree using a temporary object database; do not store "
            "objects in the repository's object database."
        ),
    )

    return parser


def _run_git(args: list[str], env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return completed.stdout


def _add_and_write_tree(env: dict[str, str]) -> str:
    _run_git(["add", "-A"], env=env)
    return _run_git(["write-tree"], env=env).strip()


if __name__ == "__main__":
    script_entry_point()
