# Development Readme for `am-common-lib`

This is the development (or inner) Readme for the `am-common-lib` project, meant
to be at `am-common-lib/am-common-lib-src/Dev-README.md`. There is also an
[outer Readme](../README.md).

## Other Documentation Files

Other documentation (typically `.md` files) should go in the `docs/` folder.
Some links:

- Project [TODOs](docs/TODO.md)
- [Scratch pad](docs/Scratch.md) during development

## Ensuring the virtual environment is in sync with the Pipfile

First change to the project's source folder:

    cd <base_path>
    cd am-common-lib/am-common-lib-src

Then

    pipenv sync --dev

## Running tests

From the project source folder,

    cd <base_path>
    cd am-common-lib/am-common-lib-src

run

    pipenv run pytest -v
    pipenv run pytest -v devenv-test

## Linting and Formatting

To get pull requests ready to merge, run:

    pipenv run format
    pipenv run chk
    pipenv run pytest -v --cov=am_common_lib --cov-branch --cov-report=term-missing --cov-report=html
    pipenv run pytest -v devenv-test
