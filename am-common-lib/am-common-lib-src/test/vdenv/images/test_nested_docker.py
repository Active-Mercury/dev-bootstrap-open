"""Verify Docker-in-Docker: the nested daemon is functional and isolated.

Every image in the chain inherits the ``docker:dind`` entrypoint that launches
``dockerd``.  These tests confirm that both ``dockeruser`` and ``root`` can
drive the nested daemon, that containers started inside are invisible to
the host, and that namespace isolation holds.
"""

from __future__ import annotations

import uuid

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from ._support import ContainerRef
from ._support import docker_exec
from ._support import docker_run
from ._support import seed_image_in_dind
from ._support import wait_for_nested_docker


pytestmark = pytest.mark.xdist_group("docker")


def test_inner_container_not_visible_on_host(
    running_container: ContainerRef,
) -> None:
    """A container inside DinD must not appear in the host's ``docker ps``."""
    c = running_container
    inner = f"vdenv-invisible-{uuid.uuid4().hex[:12]}"

    wait_for_nested_docker(c.name)

    try:
        seed_image_in_dind(c.name)
        start = docker_exec(
            c.name,
            "docker",
            "run",
            "-d",
            "--name",
            inner,
            "alpine:latest",
            "sleep",
            "60",
            user="dockeruser",
            timeout=60,
        )
        assert_that(start.returncode).described_as("returncode").is_zero()

        inner_ps = docker_exec(
            c.name,
            "docker",
            "ps",
            "--format",
            "{{.Names}}",
            user="dockeruser",
            timeout=30,
        )
        with soft_assertions():
            assert_that(inner_ps.returncode).described_as("returncode").is_zero()
            assert_that(inner_ps.stdout).described_as("stdout").contains(inner)

        host_ps = docker_run(
            "docker",
            "ps",
            "--format",
            "{{.Names}}",
            timeout=30,
        )
        with soft_assertions():
            assert_that(host_ps.returncode).described_as("returncode").is_zero()
            assert_that(host_ps.stdout).described_as("stdout").does_not_contain(inner)
    finally:
        docker_exec(
            c.name,
            "docker",
            "rm",
            "-f",
            inner,
            user="dockeruser",
            timeout=30,
        )


def test_root_can_run_inner_container(
    running_container: ContainerRef,
) -> None:
    """``root`` can run a nested container whose hostname differs from outer."""
    c = running_container
    wait_for_nested_docker(c.name)

    outer_hn = docker_exec(c.name, "hostname", user="root", timeout=10)
    with soft_assertions():
        assert_that(outer_hn.returncode).described_as("returncode").is_zero()
        assert_that(outer_hn.stdout.strip()).described_as("stdout").is_not_empty()
        assert_that(outer_hn.stderr.strip()).described_as("stderr").is_empty()

    seed_image_in_dind(c.name)
    inner_hn = docker_exec(
        c.name,
        "docker",
        "run",
        "--rm",
        "alpine:latest",
        "hostname",
        user="root",
        timeout=120,
    )
    with soft_assertions():
        assert_that(inner_hn.returncode).described_as("returncode").is_zero()
        assert_that(inner_hn.stdout.strip()).described_as("stdout").is_not_empty()
        assert_that(inner_hn.stderr.strip()).described_as("stderr").is_empty()

    assert_that(inner_hn.stdout.strip()).is_not_equal_to(outer_hn.stdout.strip())


def test_hostname_isolation(
    running_container: ContainerRef,
) -> None:
    """Inner container hostname differs from outer (as dockeruser)."""
    c = running_container
    wait_for_nested_docker(c.name)

    outer = docker_exec(c.name, "hostname", user="dockeruser", timeout=10)
    with soft_assertions():
        assert_that(outer.returncode).described_as("returncode").is_zero()
        assert_that(outer.stdout.strip()).described_as("stdout").is_not_empty()

    seed_image_in_dind(c.name)
    inner = docker_exec(
        c.name,
        "docker",
        "run",
        "--rm",
        "alpine:latest",
        "hostname",
        user="dockeruser",
        timeout=120,
    )
    with soft_assertions():
        assert_that(inner.returncode).described_as("returncode").is_zero()
        assert_that(inner.stdout.strip()).described_as("stdout").is_not_empty()
        assert_that(inner.stderr.strip()).described_as("stderr").is_empty()

    assert_that(inner.stdout.strip()).is_not_equal_to(outer.stdout.strip())


def test_inner_container_removed_after_exit(
    running_container: ContainerRef,
) -> None:
    """A ``--rm`` container inside DinD is cleaned up after it exits."""
    c = running_container
    inner = f"vdenv-rm-{uuid.uuid4().hex[:12]}"

    wait_for_nested_docker(c.name)

    seed_image_in_dind(c.name)
    run_res = docker_exec(
        c.name,
        "docker",
        "run",
        "--rm",
        "--name",
        inner,
        "alpine:latest",
        "true",
        user="dockeruser",
        timeout=60,
    )
    assert_that(run_res.returncode).described_as("returncode").is_zero()

    ps_res = docker_exec(
        c.name,
        "docker",
        "ps",
        "-a",
        "--filter",
        f"name={inner}",
        "--format",
        "{{.Names}}",
        user="dockeruser",
        timeout=30,
    )
    with soft_assertions():
        assert_that(ps_res.returncode).described_as("returncode").is_zero()
        assert_that(ps_res.stdout.strip()).described_as("stdout").is_empty()
