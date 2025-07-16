from functools import cache
import importlib.resources
from importlib.resources.abc import Traversable
import json
import subprocess

from assertpy import assert_that
from assertpy import soft_assertions
import pytest


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

    # Build the Docker image
    res1 = subprocess.run(
        ["docker", "build", "-t", image_name, str(image_dir)],
        capture_output=True,
        text=True,
    )
    assert_that(res1.returncode).is_equal_to(0).described_as(
        f"Failed to build {image_name} in {image_dir}: {res1.stderr}"
    )

    # Basic test
    res2 = subprocess.run(
        ["docker", "run", "-i", "--rm", image_name, "echo", "Hello"],
        capture_output=True,
    )
    with soft_assertions():
        assert_that(res2.returncode).is_equal_to(0)
        assert_that(res2.stdout.strip()).is_equal_to(b"Hello")
        assert_that(res2.stderr).is_equal_to(b"")
