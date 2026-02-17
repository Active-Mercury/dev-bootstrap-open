# Contribution Guidelines for `am-common-lib`

## General rules

1. Though `dev-bootstrap-closed` is the git repository toplevel, the Python
   project root is `dev-bootstrap-closed/am-common-lib/am-common-lib-src`. All
   commands referenced in these guidelines are to be run with the project root
   as the current working directory.
2. Unless otherwise stated in the specific request, you _must_ run the
   formatter-linter at least once after adding or changing sources within this
   project. Sometimes running the entire test suite is also warranted. Details
   on how to run these are in the following guidelines.
3. In running any command mentioned here, you should assume that whatever
   dependencies are required for it are satisfied and that the project is
   correctly configured to be able to run it.

## Virtual environment and package manager

4. The project uses a Python virtual environment, managed by **uv**. It uses
   `pytest` as its test framework, and exclusively uses `assertpy` assertions.
   Tests can be run thus:

   ```bash
   uv run pytest [ args ... ]
   ```

   To install all dependencies (including dev):

   ```bash
   uv sync
   ```

   To install only production dependencies:

   ```bash
   uv sync --no-group dev
   ```

## Dev tooling (`_devtools/`)

5. The `_devtools/` directory at the project root is a **separate** Python
   package that provides the `fflint` and `prettify` console scripts. It is
   installed as an editable dev dependency (`uv sync` installs it). It is _not_
   part of the distributable `am_common_lib` library. The `_devtools/` code is
   subject to the same formatting and linting rules as the rest of the project
   (it is covered by `fflint`) but is excluded from test coverage statistics
   (`--cov=am_common_lib` only measures the main library).

## Formatting, linting, and type-checking

6. The project enforces strict formatting and coding standards. The command

   ```bash
   uv run fflint
   ```

   will run the formatter-linter configured for the project. It will
   automatically run all formatting first, followed by linting of different
   kinds. This command shall be the definitive test of whether all the mandatory
   formatting and linting rules have been followed. When they have, the command
   will output no errors or warnings.
   - The project should provide docstrings for all public methods and classes,
     and the docstrings should conform strictly to the Sphinx format (i.e.,
     reST, not NumPy nor Google). Docstrings should be concise and almost never
     longer than two sentences.
   - Whenever you create a new file (often a CLI or a test file), unless
     specifically instructed not to, you must have a docstring at the top of the
     file that begins with the sentence "WARNING: This is raw AI output,
     completely UNREVIEWED, perhaps never run."
   - Never volunteer to add a docstring to a class or a method until instructed
     to by the formatter-linter. It is the final arbiter of which elements need
     docstrings and how much detail they should contain. In general, the
     requirements within the test suite are lighter than they are for the main
     library.
   - In field descriptors, prefer to combine the line for the field name with
     the line for the type, whenever the type is alphanumeric, e.g., write

     ```
     :param str name: The name
     ```

     rather than

     ```
     :param name: The name
     :type name: str
     ```

     However, whenever the type is not strictly alphanumeric (e.g., `str | None`
     or `Sequence[str]`, etc.), do maintain two separate lines (`param` and
     `type`) for that field. This will avoid confusing `pydoclint` and
     `docformatter`. For example:

     ```
     :param cwd: The current working directory
     :type cwd: str | None
     ```

   - Whenever you are making changes to the docstrings in response to output
     from the automated formatter-linter, frequently re-run the formatter-linter
     to get updated evaluations of the current state of conformity to the
     standards.
   - The project also requires strict conformity with mypy static type checks.
     The formatter-linter will let you know if there are any violations. If
     there are, fix the violations conscientiously. Try not to simply ignore the
     errors.

## Running the test suite

7. At the end of all changes, you should also make sure to run the entire test
   suite to ensure that you have not made any breaking changes:

   ```bash
   uv run pytest -v
   ```

   Tests run in parallel by default (via `pytest-xdist`). To run sequentially:

   ```bash
   uv run pytest -n 0 -v
   ```

   The devenv-test suite is run separately:

   ```bash
   uv run pytest -v devenv-test
   ```

## Coverage reports

8. The project includes `pytest-cov` and `pytest-html`. To generate a coverage
   report:

   ```bash
   # HTML coverage report (written to htmlcov/)
   uv run pytest --cov=am_common_lib --cov-report=html -v
   
   # Terminal coverage summary with missing lines
   uv run pytest --cov=am_common_lib --cov-report=term-missing -v
   ```

   After running with `--cov-report=html`, open `htmlcov/index.html` to browse
   per-file coverage.

## Running CI locally

9. To run the full CI pipeline locally (requires Docker), from the project root:

   ```bash
   python resources/run_ci_locally.py
   ```

   This will spin up a dind-dev container, clone the repository, run `fflint`,
   and execute the full test suite with coverage. The result is a tarball of
   reports in the `.ci-reports/` directory at the repository root.

## Quick reference

| Action                    | Command                                               |
| ------------------------- | ----------------------------------------------------- |
| Sync all deps             | `uv sync`                                             |
| Sync production deps only | `uv sync --no-group dev`                              |
| Run formatter-linter      | `uv run fflint`                                       |
| Run tests                 | `uv run pytest -v`                                    |
| Run devenv tests          | `uv run pytest -v devenv-test`                        |
| Run specific test file    | `uv run pytest test/<path> -v`                        |
| Run tests with coverage   | `uv run pytest --cov=am_common_lib --cov-report=html` |
| Run mypy alone            | `uv run mypy .`                                       |
| Add a production dep      | `uv add <pkg>`                                        |
| Add a dev dep             | `uv add --group dev <pkg>`                            |
| Run CI locally            | `python resources/run_ci_locally.py`                  |

## Writing a Python CLI

If you are creating a new Python CLI, let the following template be your default
starting point.

```python
"""Exemplar for a command-line interface using ArgumentParser."""

import argparse
from argparse import ArgumentParser
from collections.abc import Sequence
import os.path
import sys


def main(cmd_args: Sequence[str], prog_path: str) -> None:
    """Execute the command-line interface.

    :param cmd_args: Command arguments for the program.
    :type cmd_args: Sequence[str]
    :param str prog_path: The program path (i.e., sys.argv[0] or equivalent).
    """
    parser = _get_parser(os.path.basename(prog_path))
    parsed_args = parser.parse_args(cmd_args)

    # CHANGE THIS SECTION: Do the work here
    print(f"parsed args = {parsed_args}, prog name = {prog_path}")
    # END OF SECTION


def _get_parser(prog_name: str) -> ArgumentParser:
    parser = ArgumentParser(
        prog=prog_name,
        description="Exemplar for a command-line interface using ArgumentParser.",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, width=80),
    )

    # CHANGE THIS SECTION
    parser.add_argument("name")
    # END OF SECTION

    return parser


if __name__ == "__main__":
    main(tuple(sys.argv[1:]), sys.argv[0])
```

In addition:

- Try to keep the main method short and readable, delegating to other methods
  within the file.
- To the extent possible order the methods as follows: `main()` is always first,
  followed by all public methods, then followed by all private methods. Also
  consult the general rules for the order of methods elsewhere in this document.
- Avoid making methods public, and do so either when explicitly asked to do so,
  or it is clearly needed in other modules. Note that `main()` should always be
  public.

## Other Python Coding Guidelines

- When a timestamp is needed and human-readability is important, prefer to use

  ```python
  from datetime import datetime
  from datetime import UTC

  datetime.now(UTC).astimezone().isoformat(timespec="milliseconds")
  ```

  When human readability is not critical, prefer to use the unix time in
  milliseconds, and compute it as follows:

  ```python
  import time

  unix_time_ms = time.time_ns() // 1_000_000
  ```

- When defining module-level constants, use the Java style, e.g.,

  ```python
  from typing import Final

  DEFAULT_TIMEOUT: Final[int] = 10
  ```

### Temporary Files and Folders

Whenever you need to create a temporary directory _or_ a temporary file, use the
following template. Yes, even if all that is needed is a temporary file, prefer
to create it inside a context-managed temporary directory as follows. Naturally,
this does not apply if you have been explicitly asked to do something different
or if your needs will not be met by a `tempfile.TemporaryDirectory()`.

```python
from pathlib import Path
import tempfile


with tempfile.TemporaryDirectory() as tempdir:
    print(f"Temporary directory: {tempdir}")

    temp_path = Path(tempdir) / "my_temp_file.txt"
    temp_path.write_text("Temporary file inside a temporary directory.")
    print(f"Temporary file path: {temp_path}")
```

### Order of Methods in a Source File

- As much as possible, ensure that within a source file, all public methods
  (i.e., name starts with a letter) appear before any private methods (starting
  with a single underscore).
- Among private methods, try to sort them in order of the line number of the
  first call site within the source file.
- Among public methods, try to come up with an ordering similar to that of
  private methods, except that not all call sites are easily discoverable. So
  just try to put the most important ones or most likely to be called methods
  before others.
- By default, do not attempt any re-ordering of methods if you are merely making
  edits in existing methods. However, if you are specifically asked to reorder
  methods, then you should follow the guidelines above.
