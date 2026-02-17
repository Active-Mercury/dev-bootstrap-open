# Development Readme for `am-common-lib`

This is the development (or inner) Readme for the `am-common-lib` project, meant
to be at `am-common-lib/am-common-lib-src/Dev-README.md`. There is also an
[outer Readme](../README.md).

## Other Documentation Files

Other documentation (typically `.md` files) should go in the `docs/` folder.
Some links:

- Project [TODOs](docs/TODO.md)
- [Scratch pad](docs/Scratch.md) during development

## Ensuring the virtual environment is in sync

First change to the project's source folder:

    cd <base_path>
    cd am-common-lib/am-common-lib-src

Then

    uv sync

## Running tests

From the project source folder,

    cd <base_path>
    cd am-common-lib/am-common-lib-src

run

    uv run pytest -v
    uv run pytest -v devenv-test

## Linting and Formatting

To get pull requests ready to merge, run:

    uv run fflint
    uv run pytest -v --cov=am_common_lib --cov-branch --cov-report=term-missing --cov-report=html
    uv run pytest -v devenv-test

Key uv commands:

- `uv sync`: Install all dependencies (including dev tools) into the virtual
  environment.
- `uv sync --no-group dev`: Install only production dependencies.
- `uv run fflint`: Run the full formatter-linter pipeline (Ruff, docformatter,
  Prettier, pydoclint, mypy).
- `uv run pytest ...`: Run the test suite inside the uv-managed virtual
  environment.
- `uv add <pkg>`: Add a production dependency.
- `uv add --group dev <pkg>`: Add a dev dependency.

## Dev tooling (`_devtools/`)

The `_devtools/` directory at the project root is a **separate** Python package
that provides the `fflint` and `prettify` console scripts. It is installed as an
editable dev dependency (`uv sync` installs it). It is _not_ part of the
distributable `am_common_lib` library. The `_devtools/` code is subject to the
same formatting and linting rules as the rest of the project (it is covered by
`fflint`) but is excluded from test coverage statistics (`--cov=am_common_lib`
only measures the main library).

## Common commands

| Task                         | Command                    |
| ---------------------------- | -------------------------- |
| Install all deps (with dev)  | `uv sync`                  |
| Install only production deps | `uv sync --no-group dev`   |
| Add a production dependency  | `uv add <pkg>`             |
| Add a dev dependency         | `uv add --group dev <pkg>` |
| Remove a dependency          | `uv remove <pkg>`          |
| Run a command in the venv    | `uv run <cmd>`             |
| Run the formatter-linter     | `uv run fflint`            |
| Run the test suite           | `uv run pytest -v`         |
| Update the lock file         | `uv lock`                  |
| Show dependency tree         | `uv tree`                  |
