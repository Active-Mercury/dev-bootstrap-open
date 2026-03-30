"""Pytest fixtures for vdenv image integration tests.

Session-scoped fixtures validate that each image exists on the local Docker
host before any container is started.  The ``--dind-uv``, ``--dind-sshd``,
and ``--vdenv-ssh`` CLI options are registered in ``test/conftest.py`` so
they are available before sub-directory conftests are loaded.
"""

from __future__ import annotations

import subprocess

import pytest


def _image_exists(tag: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return result.returncode == 0


def _docker_available() -> bool:
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return result.returncode == 0


@pytest.fixture(scope="session")
def dind_uv_image(request: pytest.FixtureRequest) -> str:
    """Validated ``dind-uv`` image tag.

    Skips the session if absent.
    """
    if not _docker_available():
        pytest.skip("Docker is not available (docker info failed)")
    tag: str = request.config.getoption("--dind-uv")
    if not _image_exists(tag):
        pytest.skip(f"dind-uv image not found locally: {tag}")
    return tag


@pytest.fixture(scope="session")
def dind_sshd_image(request: pytest.FixtureRequest) -> str:
    """Validated ``dind-sshd`` image tag.

    Skips the session if absent.
    """
    if not _docker_available():
        pytest.skip("Docker is not available (docker info failed)")
    tag: str = request.config.getoption("--dind-sshd")
    if not _image_exists(tag):
        pytest.skip(f"dind-sshd image not found locally: {tag}")
    return tag


@pytest.fixture(scope="session")
def vdenv_ssh_image(request: pytest.FixtureRequest) -> str:
    """Validated ``vdenv-ssh`` image tag.

    Skips the session if absent.
    """
    if not _docker_available():
        pytest.skip("Docker is not available (docker info failed)")
    tag: str = request.config.getoption("--vdenv-ssh")
    if not _image_exists(tag):
        pytest.skip(f"vdenv-ssh image not found locally: {tag}")
    return tag


@pytest.fixture(scope="session")
def all_images(
    dind_uv_image: str,
    dind_sshd_image: str,
    vdenv_ssh_image: str,
) -> tuple[str, ...]:
    """All three validated image tags, ordered from base to product."""
    return (dind_uv_image, dind_sshd_image, vdenv_ssh_image)


@pytest.fixture(scope="session")
def sshd_capable_images(
    dind_sshd_image: str,
    vdenv_ssh_image: str,
) -> tuple[str, ...]:
    """Image tags for layers that include an SSH daemon."""
    return (dind_sshd_image, vdenv_ssh_image)
