"""Base-level guarantees that must hold for every image in the chain.

Each test is parametrized over ``dind-uv``, ``dind-sshd``, and ``vdenv-ssh``
via the ``running_container`` fixture.
"""

from __future__ import annotations

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from ._support import ContainerRef
from ._support import docker_exec


pytestmark = pytest.mark.xdist_group("docker")


def test_echo_hello(running_container: ContainerRef) -> None:
    """Container is alive and can echo back a string."""
    c = running_container
    result = docker_exec(c.name, "echo", "Hello", user="dockeruser")
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.strip()).described_as("stdout").is_equal_to("Hello")
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_dockeruser_exists(
    running_container: ContainerRef,
) -> None:
    """``dockeruser`` exists with UID != 0 and correct home/shell."""
    c = running_container

    uid_res = docker_exec(c.name, "id", "-u", "dockeruser", user="root")
    with soft_assertions():
        assert_that(uid_res.returncode).described_as("returncode").is_zero()
        assert_that(uid_res.stdout.strip()).described_as("stdout").is_not_equal_to("0")
        assert_that(uid_res.stderr).described_as("stderr").is_empty()

    passwd_res = docker_exec(c.name, "getent", "passwd", "dockeruser", user="root")
    fields = passwd_res.stdout.strip().split(":")
    with soft_assertions():
        assert_that(passwd_res.returncode).described_as("returncode").is_zero()
        assert_that(passwd_res.stderr).described_as("stderr").is_empty()
        assert_that(fields[5]).described_as("homedir").is_equal_to("/home/dockeruser")
        assert_that(fields[6]).described_as("shell").is_equal_to("/bin/bash")


def test_dockeruser_workdir(
    running_container: ContainerRef,
) -> None:
    """``pwd`` as dockeruser returns ``/home/dockeruser``."""
    c = running_container
    result = docker_exec(c.name, "pwd", user="dockeruser")
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.strip()).described_as("stdout").is_equal_to(
            "/home/dockeruser"
        )
        assert_that(result.stderr).described_as("stderr").is_empty()


def test_bash_available(
    running_container: ContainerRef,
) -> None:
    """``bash --version`` succeeds as dockeruser."""
    c = running_container
    result = docker_exec(c.name, "bash", "--version", user="dockeruser")
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.lower()).described_as("stdout").contains("bash")
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_uv_available(
    running_container: ContainerRef,
) -> None:
    """``uv --version`` succeeds and mentions uv."""
    c = running_container
    result = docker_exec(c.name, "uv", "--version", user="dockeruser")
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.lower()).described_as("stdout").contains("uv")
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_vi_available(
    sshd_running_container: ContainerRef,
) -> None:
    """``vi`` editor is present in sshd-and-higher images."""
    c = sshd_running_container
    result = docker_exec(c.name, "sh", "-c", "command -v vi", user="dockeruser")
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.strip()).described_as("stdout").ends_with("/vi")


def test_dockeruser_cannot_sudo(
    running_container: ContainerRef,
) -> None:
    """``dockeruser`` cannot use sudo (absent or denied)."""
    c = running_container
    result = docker_exec(c.name, "sudo", "true", user="dockeruser")
    error_output = f"{result.stdout}{result.stderr}".strip()
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_not_zero()
        assert_that(error_output).described_as("output").is_not_empty()
