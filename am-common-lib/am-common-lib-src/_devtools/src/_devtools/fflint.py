"""The fflint (fix, format, lint) pipeline.

Chains together formatting, linting, and type-checking tools in order:

1. ``ruff check --fix-only`` (safe auto-fixes)
2. ``docformatter`` (docstring reformatting)
3. ``ruff format`` (code formatting)
4. ``prettify`` (Prettier for non-Python files, via Docker)
5. ``ruff check`` (lint)
6. ``pydoclint`` (docstring lint)
7. ``mypy`` (static type checking)
"""

import argparse
from argparse import ArgumentParser
from collections.abc import Sequence
import os
import os.path
import sys
from typing import Final

from _devtools._combo_shell import run as _run_pipeline


_PIPELINE: Final[str] = (
    "ruff check . "
    "--select UP,I,F,A,B,C4,ERA,PIE,SIM,RET,TRY,PL "
    "--fix-only --quiet --exit-zero "
    "&& docformatter am_common_lib _devtools/src "
    "|| docformatter am_common_lib _devtools/src "
    "&& ruff format . "
    "&& prettify "
    "&& ruff check . "
    "&& pydoclint am_common_lib _devtools/src/_devtools "
    "&& mypy ."
)


def script_entry_point() -> None:
    """Console-script entry point that delegates to :func:`main`."""
    sys.exit(main(tuple(sys.argv[1:]), sys.argv[0], __name__))


def main(cmd_args: Sequence[str], prog_path: str, entry_name: str) -> int:
    """Execute the fflint pipeline.

    :param cmd_args: Command arguments for the program.
    :type cmd_args: Sequence[str]
    :param str prog_path: The program path (i.e., sys.argv[0] or equivalent).
    :param str entry_name: The ``__name__`` of the calling module.
    :return: Exit code (0 for success, non-zero for failure).
    :rtype: int
    """
    parser = _get_parser(os.path.basename(prog_path))
    parser.parse_args(cmd_args)

    project_root = _find_project_root()
    os.chdir(project_root)
    return _run_pipeline(_PIPELINE)


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


def _get_parser(prog_name: str) -> ArgumentParser:
    return ArgumentParser(
        prog=prog_name,
        description="Run the fflint (fix, format, lint) pipeline.",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, width=80),
    )


if __name__ == "__main__":
    script_entry_point()
