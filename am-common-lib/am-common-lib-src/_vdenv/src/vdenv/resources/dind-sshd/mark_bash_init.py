"""Ensure Bash init files begin with a marker echo to STDERR."""

from __future__ import annotations

from collections.abc import Sequence
import os
from pathlib import Path
import sys


def main(cmd_args: Sequence[str], prog_path: str) -> None:
    """Execute the script logic; arguments are ignored.

    :param cmd_args: Command arguments for the program (unused).
    :type cmd_args: Sequence[str]
    :param str prog_path: The program path (unused).
    """
    home = Path(os.path.expanduser("~"))
    targets = [
        ".bash_profile",
        ".bash_login",
        ".profile",
        ".bashrc",
    ]
    for name in targets:
        _ensure_marker_line(home / name, name)


def _ensure_marker_line(path: Path, filename: str) -> None:
    """Prepend an echo marker to STDERR at the top of the given file.

    If the file does not exist, it will be created. If it exists and the first line
    already matches exactly, nothing will be changed.

    :param path: The full path of the file to modify.
    :type path: Path
    :param str filename: The filename used in the printed marker.
    """
    expected = f'echo "Running ~/{filename}" >&2'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected + "\n", encoding="utf-8")
        return

    content = path.read_text(encoding="utf-8").splitlines()
    if content and content[0] == expected:
        return

    new_lines = [expected] + content
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(tuple(sys.argv[1:]), sys.argv[0])
