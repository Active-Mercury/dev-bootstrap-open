"""SSH integration tests for ``dind-sshd`` and ``vdenv-ssh``.

All SSH traffic originates from a dedicated Alpine client container so that
the host machine's ``~/.ssh`` is never touched.  The ``ssh_test_rig`` fixture
(see ``conftest.py``) handles keypair generation, ``known_hosts`` setup, and
sshd readiness probing.
"""

from __future__ import annotations

import subprocess
import time

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from ._support import docker_run
from .conftest import SshTestRig


pytestmark = pytest.mark.xdist_group("docker")

_SSH_TIMEOUT = 10


def _ssh_from_client(
    rig: SshTestRig,
    remote_cmd: str,
    *,
    user: str = "dockeruser",
    extra_opts: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute *remote_cmd* on the server via SSH from the client."""
    cmd = [
        "docker",
        "exec",
        rig.client_name,
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
        "UserKnownHostsFile=/root/.ssh/known_hosts",
        "-i",
        rig.private_key_path,
        "-p",
        rig.host_port,
        *(extra_opts or []),
        f"{user}@host.docker.internal",
        remote_cmd,
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_SSH_TIMEOUT,
    )


# ------------------------------------------------------------------
# Positive: dockeruser can SSH in
# ------------------------------------------------------------------


def test_ssh_as_dockeruser(ssh_test_rig: SshTestRig) -> None:
    """SSH as ``dockeruser`` with the injected public key succeeds."""
    res = _ssh_from_client(ssh_test_rig, "id -un")
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_zero()
        assert_that(res.stdout.strip()).described_as("stdout").is_equal_to("dockeruser")
        assert_that(res.stderr.strip()).described_as("stderr").is_empty()


# ------------------------------------------------------------------
# Negative: root login denied
# ------------------------------------------------------------------


def test_ssh_as_root_denied(ssh_test_rig: SshTestRig) -> None:
    """SSH as ``root`` must be rejected."""
    res = _ssh_from_client(ssh_test_rig, "id -un", user="root")
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_not_zero()
        assert_that(res.stdout.strip()).described_as("stdout").is_empty()
        assert_that(res.stderr.strip()).described_as("stderr").is_not_empty()


# ------------------------------------------------------------------
# Negative: password authentication denied
# ------------------------------------------------------------------


def test_ssh_password_auth_denied(
    ssh_test_rig: SshTestRig,
) -> None:
    """SSH with password authentication (no key) must be rejected."""
    cmd = [
        "docker",
        "exec",
        ssh_test_rig.client_name,
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
        "PubkeyAuthentication=no",
        "-o",
        "PasswordAuthentication=yes",
        "-o",
        "UserKnownHostsFile=/root/.ssh/known_hosts",
        "-p",
        ssh_test_rig.host_port,
        "dockeruser@host.docker.internal",
        "true",
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_SSH_TIMEOUT,
    )
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_not_zero()
        assert_that(res.stdout.strip()).described_as("stdout").is_empty()
        assert_that(res.stderr.strip()).described_as("stderr").is_not_empty()


# ------------------------------------------------------------------
# SFTP: upload and verify
# ------------------------------------------------------------------


def test_sftp_file_transfer(ssh_test_rig: SshTestRig) -> None:
    """Upload a file via SFTP and read it back over SSH."""
    rig = ssh_test_rig
    payload = "hello-from-sftp-test"

    docker_run(
        "docker",
        "exec",
        rig.client_name,
        "sh",
        "-c",
        f"printf '%s' '{payload}' > /tmp/sftp_src.txt",
    )

    docker_run(
        "docker",
        "exec",
        rig.client_name,
        "sh",
        "-c",
        "printf '%s\\n' "
        "'put /tmp/sftp_src.txt /home/dockeruser/sftp_dst.txt' "
        "> /tmp/sftp_batch.txt",
    )

    sftp_cmd = (
        "sftp "
        "-b /tmp/sftp_batch.txt "
        "-o StrictHostKeyChecking=yes "
        "-o IdentitiesOnly=yes "
        "-o LogLevel=ERROR "
        f"-o UserKnownHostsFile=/root/.ssh/known_hosts "
        f"-i {rig.private_key_path} "
        f"-P {rig.host_port} "
        "dockeruser@host.docker.internal"
    )
    sftp_res = docker_run(
        "docker",
        "exec",
        rig.client_name,
        "sh",
        "-c",
        sftp_cmd,
        timeout=_SSH_TIMEOUT,
    )
    with soft_assertions():
        assert_that(sftp_res.returncode).described_as("returncode").is_zero()
        assert_that(sftp_res.stderr.strip()).described_as("stderr").is_empty()

    cat_res = _ssh_from_client(rig, "cat /home/dockeruser/sftp_dst.txt")
    with soft_assertions():
        assert_that(cat_res.returncode).described_as("returncode").is_zero()
        assert_that(cat_res.stdout.strip()).described_as("stdout").is_equal_to(payload)
        assert_that(cat_res.stderr.strip()).described_as("stderr").is_empty()


# ------------------------------------------------------------------
# Local port forwarding
# ------------------------------------------------------------------


def test_ssh_local_port_forwarding(
    ssh_test_rig: SshTestRig,
) -> None:
    """Establish a local port forward and SSH again through it."""
    rig = ssh_test_rig
    local_port = "22222"
    control_sock = "/tmp/vdenv-tunnel.sock"

    tunnel_cmd = [
        "docker",
        "exec",
        rig.client_name,
        "ssh",
        "-M",
        "-S",
        control_sock,
        "-f",
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "UserKnownHostsFile=/root/.ssh/known_hosts",
        "-i",
        rig.private_key_path,
        "-L",
        f"127.0.0.1:{local_port}:127.0.0.1:22",
        "-p",
        rig.host_port,
        "dockeruser@host.docker.internal",
    ]
    tunnel_res = subprocess.run(
        tunnel_cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_SSH_TIMEOUT,
    )
    assert_that(tunnel_res.returncode).described_as("returncode").is_zero()

    try:
        time.sleep(1)

        nested_ssh = [
            "docker",
            "exec",
            rig.client_name,
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "LogLevel=ERROR",
            "-i",
            rig.private_key_path,
            "-p",
            local_port,
            "dockeruser@127.0.0.1",
            "id -un",
        ]
        nested_res = subprocess.run(
            nested_ssh,
            capture_output=True,
            text=True,
            check=False,
            timeout=_SSH_TIMEOUT,
        )
        with soft_assertions():
            assert_that(nested_res.returncode).described_as("returncode").is_zero()
            assert_that(nested_res.stdout.strip()).described_as("stdout").is_equal_to(
                "dockeruser"
            )
            assert_that(nested_res.stderr.strip()).described_as("stderr").is_empty()
    finally:
        subprocess.run(
            [
                "docker",
                "exec",
                rig.client_name,
                "ssh",
                "-S",
                control_sock,
                "-O",
                "exit",
                "-p",
                rig.host_port,
                "dockeruser@host.docker.internal",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SSH_TIMEOUT,
        )


# ------------------------------------------------------------------
# Docker reachable over SSH
# ------------------------------------------------------------------


def test_docker_over_ssh(ssh_test_rig: SshTestRig) -> None:
    """``docker info`` succeeds over SSH, confirming the nested daemon is reachable
    after login."""
    res = _ssh_from_client(ssh_test_rig, "docker info")
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_zero()
        assert_that(res.stdout).described_as("stdout").is_not_empty()
        # docker info emits blkio warnings on stderr; not a failure.
        assert_that(res.stderr).described_as("stderr").does_not_contain("error")
