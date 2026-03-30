"""Root test conftest -- registers CLI options needed early by pytest.

Options defined here are available before sub-directory conftests are loaded,
which is required for ``pytest_addoption`` hooks to work with command-line
arguments.
"""

from __future__ import annotations

from typing import Final

import pytest


_VDENV_OPTION_DEFAULTS: Final[dict[str, str]] = {
    "dind_uv": "dind-uv:latest",
    "dind_sshd": "dind-sshd:latest",
    "vdenv_ssh": "vdenv-ssh:latest",
}


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register ``--dind-uv``, ``--dind-sshd``, ``--vdenv-ssh`` CLI options."""
    group = parser.getgroup("vdenv", "vdenv image integration tests")
    group.addoption(
        "--dind-uv",
        default=_VDENV_OPTION_DEFAULTS["dind_uv"],
        help="Image tag or digest for the dind-uv base image (default: %(default)s)",
    )
    group.addoption(
        "--dind-sshd",
        default=_VDENV_OPTION_DEFAULTS["dind_sshd"],
        help="Image tag or digest for the dind-sshd image (default: %(default)s)",
    )
    group.addoption(
        "--vdenv-ssh",
        default=_VDENV_OPTION_DEFAULTS["vdenv_ssh"],
        help="Image tag or digest for the vdenv-ssh product image "
        "(default: %(default)s)",
    )
