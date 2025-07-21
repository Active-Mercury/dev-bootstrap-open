from contextlib import nullcontext
from functools import cache
import importlib.resources
from importlib.resources.abc import Traversable
import json
from pathlib import Path
import shlex
import subprocess
from typing import ContextManager, Generator, Tuple

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from am_common_lib.docker_util import ImageNames
from am_common_lib.docker_util.docker_runner import DockerRunner


@cache
def docker_images_root() -> Traversable:
    return importlib.resources.files("resources").joinpath("docker-images")


def test_images_dir_exists() -> None:
    assert_that(docker_images_root().is_dir()).described_as(
        f"'resources/docker-images' directory not found at {docker_images_root()!r}"
    )


# Gather all subdirectories under docker-images to use as parameterized cases
IMAGE_DIRS = [path for path in docker_images_root().iterdir() if path.is_dir()]


@pytest.mark.parametrize(
    "image_dir", IMAGE_DIRS, ids=[path.name for path in IMAGE_DIRS]
)
def test_build_docker_image(image_dir: Traversable) -> None:
    """Build a single Docker image from its directory and assert success."""
    # Ensure a Dockerfile is present
    dockerfile = image_dir.joinpath("Dockerfile")
    assert_that(dockerfile.is_file()).described_as(
        f"Dockerfile missing in {image_dir.name}"
    )

    # Ensure image_info.json is present
    info_json = image_dir.joinpath("image_info.json")
    assert_that(info_json.is_file()).described_as(
        f"image_info.json missing in {image_dir.name}"
    )

    # Load image metadata
    with info_json.open("r") as f:
        info = json.load(f)
    image_name = info.get("image_name")
    assert_that(image_name).is_not_empty().described_as(
        f"'image_name' missing or empty in {info_json}"
    )

    if not info.get("active", False):
        pytest.skip(f"Skipping {image_dir.name} because it is not active")

    ctx: ContextManager[Path | Traversable]
    if info.get("extract", False):
        ctx = importlib.resources.as_file(image_dir)
    else:
        ctx = nullcontext(image_dir)

    with ctx as alias_img_dir:
        # Build the Docker image
        res1 = subprocess.run(
            ["docker", "build", "-t", image_name, str(alias_img_dir)],
            capture_output=True,
            text=True,
        )
        assert_that(res1.returncode).is_equal_to(0).described_as(
            f"Failed to build {image_name} in {alias_img_dir}: {res1.stderr}"
        )

        # Basic test
        cmd_args = [
            "docker",
            "run",
            "-i",
            *info.get("run_args", []),
            "--rm",
            image_name,
            "echo",
            "Hello",
        ]
        print(shlex.join(cmd_args))
        res2 = subprocess.run(
            cmd_args,
            capture_output=True,
        )
        with soft_assertions():
            assert_that(res2.returncode).described_as("returncode").is_equal_to(0)
            assert_that(res2.stdout.strip()).described_as("stdout").is_equal_to(
                b"Hello"
            )
            assert_that(res2.stderr).described_as("stderr").is_equal_to(b"")


@pytest.fixture(scope="class")
def docker_oo_docker_container() -> Generator[Tuple[DockerRunner, str], None, None]:
    extra_args = [
        "-v",
        "/var/run/docker.sock:/var/run/docker.sock",
        "-w",
        "/home/superuser",
    ]
    with DockerRunner(ImageNames.PYTHON_DEV_DOCKER_CLI, run_args=extra_args) as c:
        res = c.run(["hostname"], text=True)
        with soft_assertions():
            assert_that(res.returncode).described_as("returncode").is_equal_to(0)
            host_name = res.stdout.strip()
            assert_that(host_name).described_as("stdout").is_not_empty()
            assert_that(res.stderr).described_as("stderr").is_equal_to("")

        yield c, host_name


def test_dood_parent_docker_runner_root(
    docker_oo_docker_container: Tuple[DockerRunner, str],
) -> None:
    runner, host_name = docker_oo_docker_container
    res = runner.run(["id", "-un"], text=True)
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        assert_that(res.stdout.strip()).described_as("stdout").is_equal_to("root")
        assert_that(res.stderr).described_as("stderr").is_equal_to("")

    res = runner.run(["pwd"], text=True)
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        # TODO: Why is this?
        assert_that(res.stdout.strip()).described_as("stdout").is_equal_to(
            "/home/superuser"
        )
        assert_that(res.stderr).described_as("stderr").is_equal_to("")

    res = runner.run(
        ["docker", "run", "-i", "--rm", ImageNames.PYTHON_DEV, "hostname"], text=True
    )
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        inner_host_name = res.stdout.strip()
        assert_that(res.stdout.strip()).described_as("stdout").is_not_empty()
        assert_that(res.stderr).described_as("stderr").is_equal_to("")

    assert_that(inner_host_name).is_not_equal_to(host_name)


def test_dood_superuser(
    docker_oo_docker_container: Tuple[DockerRunner, str],
) -> None:
    runner, host_name = docker_oo_docker_container
    user_view = runner.use_as("superuser")
    res = user_view.run(["id", "-un"], text=True)
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        assert_that(res.stdout.strip()).described_as("stdout").is_equal_to("superuser")
        assert_that(res.stderr).described_as("stderr").is_equal_to("")

    res = user_view.run(["pwd"], text=True)
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        assert_that(res.stdout.strip()).described_as("stdout").is_equal_to(
            "/home/superuser"
        )
        assert_that(res.stderr).described_as("stderr").is_equal_to("")

    res = user_view.run(
        ["sudo", "docker", "run", "-i", "--rm", ImageNames.PYTHON_DEV, "hostname"],
        text=True,
    )
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        inner_host_name = res.stdout.strip()
        assert_that(res.stdout.strip()).described_as("stdout").is_not_empty()
        assert_that(res.stderr).described_as("stderr").is_equal_to("")

    assert_that(inner_host_name).is_not_equal_to(host_name)


def test_dood_dockeruser(
    docker_oo_docker_container: Tuple[DockerRunner, str],
) -> None:
    runner, host_name = docker_oo_docker_container
    user_view = runner.use_as("dockeruser")
    res = user_view.run(["id", "-un"], text=True)
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        assert_that(res.stdout.strip()).described_as("stdout").is_equal_to("dockeruser")
        assert_that(res.stderr).described_as("stderr").is_equal_to("")

    res = user_view.run(["pwd"], text=True)
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        assert_that(res.stdout.strip()).described_as("stdout").is_equal_to(
            "/home/dockeruser"
        )
        assert_that(res.stderr).described_as("stderr").is_equal_to("")

    # This should succeed though dockeruser cannot sudo
    res = runner.run(
        ["docker", "run", "-i", "--rm", ImageNames.PYTHON_DEV, "hostname"],
        text=True,
    )
    with soft_assertions():
        assert_that(res.returncode).described_as("returncode").is_equal_to(0)
        inner_host_name = res.stdout.strip()
        assert_that(res.stdout.strip()).described_as("stdout").is_not_empty()
        assert_that(res.stderr).described_as("stderr").is_equal_to("")

    assert_that(inner_host_name).is_not_equal_to(host_name)
