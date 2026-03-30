"""Developer-tool guarantees exclusive to ``vdenv-ssh``.

The product image must provide common developer utilities and a working
``python3`` that resolves to 3.13.  Additionally, Python tools like
``ruff`` and ``pipenv`` must be runnable via ``uv tool run`` inside the
container (online).
"""

from __future__ import annotations

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from ._support import ContainerRef
from ._support import docker_exec


pytestmark = pytest.mark.xdist_group("docker")


def test_git_available(
    vdenv_only_container: ContainerRef,
) -> None:
    """``git --version`` succeeds as dockeruser."""
    c = vdenv_only_container
    result = docker_exec(c.name, "git", "--version", user="dockeruser")
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.lower()).described_as("stdout").contains("git")
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_make_available(
    vdenv_only_container: ContainerRef,
) -> None:
    """``make --version`` succeeds as dockeruser."""
    c = vdenv_only_container
    result = docker_exec(c.name, "make", "--version", user="dockeruser")
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.lower()).described_as("stdout").contains("make")
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_python3_defaults_to_3_13(
    vdenv_only_container: ContainerRef,
) -> None:
    """``python3 --version`` reports 3.13.x."""
    c = vdenv_only_container
    result = docker_exec(
        c.name,
        "python3",
        "--version",
        user="dockeruser",
    )
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.strip()).described_as("stdout").matches(
            r"Python 3\.13\.\d+"
        )
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_pipenv_installable(
    vdenv_only_container: ContainerRef,
) -> None:
    """``pipenv`` can be installed via ``uv tool install`` and reports its version."""
    c = vdenv_only_container
    script = "uv tool install pipenv && pipenv --version"
    result = docker_exec(
        c.name,
        "sh",
        "-lc",
        script,
        user="dockeruser",
        timeout=300,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(combined.lower()).described_as("output").contains("pipenv")


def test_jq_available(
    vdenv_only_container: ContainerRef,
) -> None:
    """``jq`` can parse a trivial JSON snippet."""
    c = vdenv_only_container
    result = docker_exec(
        c.name,
        "sh",
        "-c",
        "echo '{\"a\":1}' | jq .a",
        user="dockeruser",
    )
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.strip()).described_as("stdout").is_equal_to("1")
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_rg_available(
    vdenv_only_container: ContainerRef,
) -> None:
    """``rg --version`` succeeds as dockeruser."""
    c = vdenv_only_container
    result = docker_exec(c.name, "rg", "--version", user="dockeruser")
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.lower()).described_as("stdout").contains("ripgrep")
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_npx_available(
    vdenv_only_container: ContainerRef,
) -> None:
    """``npx --version`` succeeds as dockeruser."""
    c = vdenv_only_container
    result = docker_exec(c.name, "npx", "--version", user="dockeruser")
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.strip()).described_as("stdout").is_not_empty()
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_compile_and_run_c_offline(
    vdenv_only_offline_container: ContainerRef,
) -> None:
    """Compile and execute a trivial C program in an offline container."""
    c = vdenv_only_offline_container
    script = (
        "printf '%s\\n'"
        " '#include <stdio.h>'"
        " 'int main(void) { puts(\"hello-c\"); return 0; }'"
        " > /tmp/hello.c"
        " && gcc -o /tmp/hello /tmp/hello.c"
        " && /tmp/hello"
    )
    result = docker_exec(
        c.name,
        "sh",
        "-c",
        script,
        user="dockeruser",
        timeout=60,
    )
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.strip()).described_as("stdout").is_equal_to("hello-c")
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


def test_compile_and_run_cpp_offline(
    vdenv_only_offline_container: ContainerRef,
) -> None:
    """Compile and execute a trivial C++ program in an offline container."""
    c = vdenv_only_offline_container
    script = (
        "printf '%s\\n'"
        " '#include <iostream>'"
        " 'int main() { std::cout << \"hello-cpp\" << std::endl; }'"
        " > /tmp/hello.cpp"
        " && g++ -o /tmp/hellocpp /tmp/hello.cpp"
        " && /tmp/hellocpp"
    )
    result = docker_exec(
        c.name,
        "sh",
        "-c",
        script,
        user="dockeruser",
        timeout=60,
    )
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.strip()).described_as("stdout").is_equal_to(
            "hello-cpp"
        )
        assert_that(result.stderr.strip()).described_as("stderr").is_empty()


# ------------------------------------------------------------------
# Installable tools (not baked in; may be promoted to baked-in later)
# ------------------------------------------------------------------


def test_patch_installable(
    vdenv_only_container: ContainerRef,
) -> None:
    """GNU ``patch`` can be installed and used inside the container."""
    c = vdenv_only_container
    script = "apk add --no-cache patch >/dev/null 2>&1 && patch --version"
    result = docker_exec(
        c.name,
        "sh",
        "-c",
        script,
        user="root",
        timeout=120,
    )
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.lower()).described_as("stdout").contains("patch")


def test_diffutils_installable(
    vdenv_only_container: ContainerRef,
) -> None:
    """GNU ``diff`` (from diffutils) can be installed and used."""
    c = vdenv_only_container
    script = "apk add --no-cache diffutils >/dev/null 2>&1 && diff --version"
    result = docker_exec(
        c.name,
        "sh",
        "-c",
        script,
        user="root",
        timeout=120,
    )
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(result.stdout.lower()).described_as("stdout").contains("diff")


def test_uv_tool_run_ruff(
    vdenv_only_container: ContainerRef,
) -> None:
    """``uv tool run ruff --version`` succeeds (online) as dockeruser.

    Verifies that ``uv tool run`` can fetch and execute a musl-compatible
    Python tool inside the Alpine container.  ``taplo`` is intentionally
    excluded because its PyPI wheels are glibc-only (manylinux).
    """
    c = vdenv_only_container
    result = docker_exec(
        c.name,
        "sh",
        "-c",
        "uv tool run ruff --version",
        user="dockeruser",
        timeout=300,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    with soft_assertions():
        assert_that(result.returncode).described_as("returncode").is_zero()
        assert_that(combined.lower()).described_as("output").contains("ruff")
