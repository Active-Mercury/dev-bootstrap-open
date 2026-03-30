"""Verify pre-installed Python interpreters work offline.

Each image in the chain must provide Python 3.9, 3.11, and 3.13 via
``uv python install`` at build time.  Tests run inside **network-disconnected**
containers (via the ``offline_container`` fixture) to prove the interpreters
are genuinely pre-installed and do not require a download at runtime.
"""

from __future__ import annotations

import json
from typing import Final

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from ._support import ContainerRef
from ._support import docker_exec


pytestmark = pytest.mark.xdist_group("docker")

_PYTHON_MINORS: Final[list[int]] = [9, 11, 13]


@pytest.mark.parametrize(
    "minor",
    _PYTHON_MINORS,
    ids=[f"py3.{m}" for m in _PYTHON_MINORS],
)
def test_python_version_offline(
    offline_container: ContainerRef,
    minor: int,
) -> None:
    """``uv run --python 3.X`` succeeds offline and reports the correct version,
    ``ssl``, and ``sqlite3`` availability."""
    c = offline_container

    py_check = (
        "import json, ssl, sqlite3, sys; "
        "print(json.dumps({"
        '"version": list(sys.version_info), '
        '"sqlite": sqlite3.sqlite_version, '
        '"openssl": ssl.OPENSSL_VERSION}))'
    )
    uv_cmd = f"uv run --no-project --python 3.{minor} -- python -c {repr(py_check)}"
    result = docker_exec(
        c.name,
        "sh",
        "-c",
        uv_cmd,
        user="dockeruser",
        timeout=60,
    )

    payload: dict[str, object] = {}
    try:
        raw = result.stdout.strip()
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
    except (json.JSONDecodeError, TypeError):
        payload = {}

    ver_raw = payload.get("version")
    version = (
        tuple(ver_raw[:3])
        if isinstance(ver_raw, list) and len(ver_raw) >= 3
        else (0, 0, 0)
    )

    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()
        assert_that(version >= (3, minor, 0)).described_as("min").is_true()
        assert_that(version < (3, minor + 1, 0)).described_as("max").is_true()

    with soft_assertions():
        assert_that(payload.get("sqlite")).described_as("sqlite").is_instance_of(
            str
        ).is_not_empty()
        assert_that(payload.get("openssl")).described_as("openssl").is_instance_of(
            str
        ).is_not_empty()
