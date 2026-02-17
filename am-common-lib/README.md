# Readme for `am-common-lib`

This is the _outer_ project README. The content here should be limited to

- Information a developer might need _before_ opening the project in an IDE.
- Help with setting up (or syncing) the virtual environment.
- Packaging and running tests outside of an IDE.
- Any documentation that must be attached to a distribution package.

There is also a [development README](am-common-lib-src/Dev-README.md), for
everything else.

## Initializing the dev environment

First change to the project's source folder:

    cd <base_path>
    cd am-common-lib/am-common-lib-src

Then

    uv sync

The virtual environment should be ready now. Confirm this by running the tests
for the project.

## Running tests

From the project source folder,

    cd <base_path>
    cd am-common-lib/am-common-lib-src

run

    uv run pytest -v

## Packaging

To create a distribution package, run

    cd <base_path>/am-common-lib/am-common-lib-src
    uv build
