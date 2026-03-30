"""Fixtures for vdenv image integration tests.

Provides parametrized container fixtures that implement the upward-inheritance
rule: base-level tests run against all three images, SSH tests run against
``dind-sshd`` and ``vdenv-ssh``, and product-level tests run against
``vdenv-ssh`` only.

SSH tests use a separate Alpine container as the client so that keypair
material and known-hosts entries never touch the host machine.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time

from assertpy import assert_that
import pytest

from ._support import ContainerRef
from ._support import docker_exec
from ._support import docker_run
from ._support import tmp_container
from ._support import wait_for_container_exec
from ._support import wait_for_nested_docker


def _worker_suffix(request: pytest.FixtureRequest) -> str:
    """Return a short suffix incorporating xdist worker id (if any)."""
    wid = getattr(request.config, "workerinput", {}).get("workerid", "")
    return f"-{wid}" if wid else ""


def _short_image_name(tag: str) -> str:
    return tag.split(":", maxsplit=1)[0].replace("/", "-")


@pytest.fixture(
    scope="module",
    params=[0, 1, 2],
    ids=["dind-uv", "dind-sshd", "vdenv-ssh"],
)
def running_container(
    request: pytest.FixtureRequest,
    all_images: tuple[str, ...],
) -> Generator[ContainerRef]:
    """Privileged container from each image in the chain."""
    image = all_images[request.param]
    mod = Path(request.module.__file__).stem
    suffix = _worker_suffix(request)
    name = f"vdenv-test-{_short_image_name(image)}-{mod}{suffix}"

    with tmp_container(image, name=name, privileged=True) as n:
        yield ContainerRef(name=n, image=image)


@pytest.fixture(
    scope="module",
    params=[0, 1, 2],
    ids=["dind-uv", "dind-sshd", "vdenv-ssh"],
)
def offline_container(
    request: pytest.FixtureRequest,
    all_images: tuple[str, ...],
) -> Generator[ContainerRef]:
    """Privileged container disconnected from all networks after startup.

    Used by tests that must prove features work offline (e.g. pre-installed Python
    interpreters).
    """
    image = all_images[request.param]
    mod = Path(request.module.__file__).stem
    suffix = _worker_suffix(request)
    name = f"vdenv-offline-{_short_image_name(image)}-{mod}{suffix}"

    with tmp_container(image, name=name, privileged=True) as n:
        wait_for_nested_docker(n, timeout_s=60)
        docker_run("docker", "network", "disconnect", "bridge", n)
        yield ContainerRef(name=n, image=image)


@pytest.fixture(
    scope="module",
    params=[0, 1],
    ids=["dind-sshd", "vdenv-ssh"],
)
def sshd_running_container(
    request: pytest.FixtureRequest,
    sshd_capable_images: tuple[str, ...],
) -> Generator[ContainerRef]:
    """Privileged container from each SSH-capable image."""
    image = sshd_capable_images[request.param]
    mod = Path(request.module.__file__).stem
    suffix = _worker_suffix(request)
    name = f"vdenv-sshd-{_short_image_name(image)}-{mod}{suffix}"

    with tmp_container(image, name=name, privileged=True) as n:
        yield ContainerRef(name=n, image=image)


@pytest.fixture(scope="module")
def vdenv_only_container(
    request: pytest.FixtureRequest,
    vdenv_ssh_image: str,
) -> Generator[ContainerRef]:
    """Single privileged ``vdenv-ssh`` container."""
    suffix = _worker_suffix(request)
    mod = Path(request.module.__file__).stem
    name = f"vdenv-product-{mod}{suffix}"

    with tmp_container(vdenv_ssh_image, name=name, privileged=True) as n:
        yield ContainerRef(name=n, image=vdenv_ssh_image)


@pytest.fixture(scope="module")
def vdenv_only_offline_container(
    request: pytest.FixtureRequest,
    vdenv_ssh_image: str,
) -> Generator[ContainerRef]:
    """Offline ``vdenv-ssh`` container (network disconnected)."""
    suffix = _worker_suffix(request)
    mod = Path(request.module.__file__).stem
    name = f"vdenv-product-offline-{mod}{suffix}"

    with tmp_container(vdenv_ssh_image, name=name, privileged=True) as n:
        wait_for_nested_docker(n, timeout_s=60)
        docker_run("docker", "network", "disconnect", "bridge", n)
        yield ContainerRef(name=n, image=vdenv_ssh_image)


@dataclass(frozen=True)
class SshTestRig:
    """Both containers and credentials for an SSH integration test."""

    server_name: str
    server_image: str
    client_name: str
    host_port: str
    private_key_path: str
    public_key: str


@pytest.fixture(
    scope="module",
    params=[0, 1],
    ids=["dind-sshd", "vdenv-ssh"],
)
def ssh_test_rig(
    request: pytest.FixtureRequest,
    sshd_capable_images: tuple[str, ...],
) -> Generator[SshTestRig]:
    """Spin up a server container with SSH and an Alpine client.

    - Generates an Ed25519 keypair inside the client.
    - Injects the public key via ``DOCKERUSER_PUBLIC_KEY``.
    - Configures ``known_hosts`` inside the client.
    - Waits for ``sshd`` readiness.
    """
    image = sshd_capable_images[request.param]
    mod = Path(request.module.__file__).stem
    suffix = _worker_suffix(request)
    short = _short_image_name(image)
    server_name = f"vdenv-ssh-srv-{short}-{mod}{suffix}"
    client_name = f"vdenv-ssh-cli-{short}-{mod}{suffix}"

    docker_run("docker", "rm", "-f", server_name)
    docker_run("docker", "rm", "-f", client_name)
    try:
        cli_start = docker_run(
            "docker",
            "run",
            "-d",
            "--name",
            client_name,
            "alpine:latest",
            "sleep",
            "infinity",
        )
        assert_that(cli_start.returncode).described_as("returncode").is_zero()
        wait_for_container_exec(client_name, timeout_s=15)

        docker_exec(
            client_name,
            "apk",
            "add",
            "--no-cache",
            "openssh-client",
            user="root",
            timeout=120,
        )

        gw = docker_run(
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}",
            client_name,
        )
        gateway_ip = gw.stdout.strip()
        assert_that(gateway_ip).is_not_empty()
        docker_exec(
            client_name,
            "sh",
            "-c",
            f"printf '%s %s\\n' '{gateway_ip}' 'host.docker.internal' >> /etc/hosts",
            user="root",
        )

        docker_exec(
            client_name,
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            "/root/.ssh/id_ed25519",
            "-N",
            "",
            "-C",
            "vdenv-test",
            user="root",
        )
        pub_res = docker_exec(
            client_name,
            "cat",
            "/root/.ssh/id_ed25519.pub",
            user="root",
        )
        public_key = pub_res.stdout.strip()
        assert_that(public_key).is_not_empty()

        srv_start = docker_run(
            "docker",
            "run",
            "-d",
            "--privileged",
            "--name",
            server_name,
            "-P",
            "-e",
            f"DOCKERUSER_PUBLIC_KEY={public_key}",
            image,
        )
        assert_that(srv_start.returncode).described_as("returncode").is_zero()

        port_res = docker_run(
            "docker",
            "inspect",
            "-f",
            '{{ (index (index .NetworkSettings.Ports "22/tcp") 0).HostPort }}',
            server_name,
        )
        host_port = port_res.stdout.strip()
        assert_that(host_port).is_not_empty()

        key_line = ""
        for _ in range(30):
            hk = docker_exec(
                server_name,
                "sh",
                "-c",
                "cat /etc/ssh/ssh_host_ed25519_key.pub 2>/dev/null || true",
                user="root",
                timeout=10,
            )
            if hk.returncode == 0 and hk.stdout.strip():
                key_line = hk.stdout.strip()
                break
            time.sleep(1)
        assert_that(key_line).is_not_empty()
        parts = key_line.split()
        docker_exec(
            client_name,
            "sh",
            "-c",
            "mkdir -p /root/.ssh && "
            f"printf '%s %s %s\\n' "
            f"'[host.docker.internal]:{host_port}' "
            f"'{parts[0]}' '{parts[1]}' "
            "> /root/.ssh/known_hosts",
            user="root",
        )

        _wait_for_ssh(
            client_name,
            host_port,
            "/root/.ssh/id_ed25519",
            timeout_s=30,
        )

        yield SshTestRig(
            server_name=server_name,
            server_image=image,
            client_name=client_name,
            host_port=host_port,
            private_key_path="/root/.ssh/id_ed25519",
            public_key=public_key,
        )
    finally:
        docker_run("docker", "rm", "-f", server_name)
        docker_run("docker", "rm", "-f", client_name)


def _wait_for_ssh(
    client_container: str,
    host_port: str,
    identity_file: str,
    *,
    timeout_s: int = 30,
) -> None:
    """Probe SSH from *client_container* until success or timeout."""
    probe_cmd = [
        "docker",
        "exec",
        client_container,
        "ssh",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "ConnectTimeout=2",
        "-o",
        "UserKnownHostsFile=/root/.ssh/known_hosts",
        "-i",
        identity_file,
        "-p",
        host_port,
        "dockeruser@host.docker.internal",
        "true",
    ]
    for _attempt in range(timeout_s):
        result = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    logs = docker_run("docker", "logs", client_container)
    msg = (
        f"SSH not reachable within {timeout_s}s "
        f"from {client_container}; "
        f"last stderr: {result.stderr}; "  # noqa: F821
        f"client logs: {logs.stdout}{logs.stderr}"
    )
    raise AssertionError(msg)
