"""Minimal subprocess helpers for vdenv image integration tests."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
import subprocess
import time


@dataclass(frozen=True)
class ContainerRef:
    """A running container identified by name and source image tag."""

    name: str
    image: str


def docker_run(
    *args: str,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run an arbitrary Docker (or other) command, returning the result."""
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def docker_exec(
    container: str,
    *cmd: str,
    user: str = "dockeruser",
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """``docker exec -u <user>`` inside *container*."""
    return docker_run("docker", "exec", "-u", user, container, *cmd, timeout=timeout)


def wait_for_container_exec(container: str, *, timeout_s: int = 30) -> None:
    """Poll ``docker exec <container> true`` until it succeeds.

    Raises :class:`AssertionError` if the container does not become ready
    within *timeout_s* seconds.
    """
    deadline = time.monotonic() + timeout_s
    interval = 0.25
    while time.monotonic() < deadline:
        result = docker_run("docker", "exec", container, "true", timeout=10)
        if result.returncode == 0:
            return
        time.sleep(interval)
        interval = min(interval * 2, 2.0)
    msg = f"Container {container!r} not ready within {timeout_s}s"
    raise AssertionError(msg)


def wait_for_nested_docker(
    container: str,
    *,
    timeout_s: int = 90,
) -> None:
    """Wait until ``docker info`` succeeds inside *container*."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = docker_exec(container, "docker", "info", user="dockeruser", timeout=30)
        if result.returncode == 0:
            return
        time.sleep(1.0)
    msg = f"Nested Docker daemon in {container!r} not ready within {timeout_s}s"
    raise AssertionError(msg)


def seed_image_in_dind(
    container: str,
    image: str = "alpine:latest",
    *,
    timeout: int = 120,
) -> None:
    """Transfer *image* from the host daemon into the nested DinD daemon.

    Uses ``docker save | docker exec -i ... docker load`` so the nested daemon
    never needs to pull from a registry (avoiding Docker Hub rate limits).
    """
    save = subprocess.Popen(
        ["docker", "save", image],
        stdout=subprocess.PIPE,
    )
    load = subprocess.run(
        ["docker", "exec", "-i", container, "docker", "load"],
        stdin=save.stdout,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    save.wait()
    if load.returncode != 0:
        raise RuntimeError(
            f"Failed to load {image!r} into {container!r}: {load.stderr}"
        )


@contextmanager
def tmp_container(
    image: str,
    *,
    name: str,
    privileged: bool = False,
    env: dict[str, str] | None = None,
    publish_all: bool = False,
    network: str | None = None,
    ready_timeout_s: int = 30,
) -> Generator[str]:
    """Start a detached container, wait for ``exec``, yield its name.

    Unconditionally ``docker rm -f`` on exit.
    """
    cmd: list[str] = ["docker", "run", "-d", "--name", name]
    if privileged:
        cmd.append("--privileged")
    if publish_all:
        cmd.append("-P")
    if network is not None:
        cmd.extend(["--network", network])
    for k, v in (env or {}).items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.append(image)

    docker_run("docker", "rm", "-f", name)
    try:
        start = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if start.returncode != 0:
            raise RuntimeError(
                f"docker run failed for {image!r} "
                f"(exit {start.returncode}): {start.stderr}"
            )
        wait_for_container_exec(name, timeout_s=ready_timeout_s)
        yield name
    finally:
        docker_run("docker", "rm", "-f", name)
