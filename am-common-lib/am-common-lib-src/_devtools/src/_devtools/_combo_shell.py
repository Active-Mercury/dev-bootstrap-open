"""A bash-like mini-shell for cross-platform command chaining.

Command execution closely mimics basic bash-like shell behavior with respect to
the operators ``&&``, ``||``, and ``;``.  However, this is a pure Python
implementation that does not depend on bash or any other shell.
"""

import shlex
import subprocess
import sys


def run(command_string: str) -> int:  # noqa: C901
    """Execute a pipeline command string and return the exit code.

    :param str command_string: The command pipeline to execute.
    :return: The exit code of the last executed command.
    :rtype: int
    """
    tokens = shlex.split(command_string)

    commands: list[list[str]] = []
    current_cmd: list[str] = []
    operators: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ("&&", "||", ";"):
            commands.append(current_cmd)
            operators.append(token)
            current_cmd = []
        else:
            current_cmd.append(token)
        i += 1
    if current_cmd:
        commands.append(current_cmd)

    last_exit_code = 0
    for idx, cmd in enumerate(commands):
        if idx > 0:
            op = operators[idx - 1]
            if op == "&&" and last_exit_code != 0:
                continue
            if op == "||" and last_exit_code == 0:
                continue

        print(f"Running: {' '.join(cmd)}", file=sys.stderr)
        try:
            result = subprocess.run(cmd, check=True)
            last_exit_code = result.returncode
        except subprocess.CalledProcessError as e:
            last_exit_code = e.returncode
            print(
                f"Command failed with exit code {e.returncode}: {' '.join(cmd)}",
                file=sys.stderr,
            )

    return last_exit_code


def main() -> None:
    """Entry point for standalone CLI usage."""
    if len(sys.argv) != 2:
        print(
            "Usage: "
            f'{sys.argv[0]} "<command1> && <command2> || <command3> ; <command4>"\n'
            "Mimics 'bash -c' behavior for command chaining, "
            "but runs natively in Python.\n"
            "Supports:\n"
            "  &&    Run next command only if the previous succeeded\n"
            "  ||    Run next command only if the previous failed\n"
            "   ;    Always run the next command",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(run(sys.argv[1]))


if __name__ == "__main__":
    main()
