from collections import defaultdict
from collections import deque
from collections.abc import Generator
from contextlib import AbstractContextManager
from contextlib import nullcontext
from functools import cache
import importlib.resources
from importlib.resources.abc import Traversable
import json
from pathlib import Path
import shlex
import subprocess

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from am_common_lib.docker_util import ImageNames
from am_common_lib.docker_util.docker_runner import DockerRunner


pytestmark = pytest.mark.xdist_group("docker")


@cache
def image_dirs() -> list[Traversable]:
    return _topologically_sort_images(
        [path for path in docker_images_root().iterdir() if path.is_dir()]
    )


def _build_dependency_graph(
    unsorted_image_dirs: list[Traversable],
) -> tuple[dict[str, Traversable], dict[str, set[str]], dict[str, set[str]]]:
    """Build graph structures from image metadata."""
    name_to_dir: dict[str, Traversable] = {}
    dependencies: dict[str, set[str]] = defaultdict(set)
    reverse_deps: dict[str, set[str]] = defaultdict(set)

    for d in unsorted_image_dirs:
        info_file = d.joinpath("image_info.json")
        if not info_file.is_file():
            continue
        with info_file.open("r", encoding="utf-8") as f:
            info = json.load(f)

        img_name = info.get("image_name")
        if not img_name:
            continue

        name_to_dir[img_name] = d
        for dep in info.get("depends_on", []):
            dependencies[img_name].add(dep)
            reverse_deps[dep].add(img_name)

    return name_to_dir, dependencies, reverse_deps


def _kahn_sort(
    name_to_dir: dict[str, Traversable],
    dependencies: dict[str, set[str]],
    reverse_deps: dict[str, set[str]],
) -> list[Traversable]:
    """Return nodes in topological order using Kahn's algorithm."""
    indegree: dict[str, int] = {name: len(deps) for name, deps in dependencies.items()}
    for name in name_to_dir:
        indegree.setdefault(name, 0)

    queue = deque([name for name, deg in indegree.items() if deg == 0])
    sorted_names: list[str] = []

    while queue:
        node = queue.popleft()
        sorted_names.append(node)
        for child in reverse_deps.get(node, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(sorted_names) < len(name_to_dir):
        missing = set(name_to_dir) - set(sorted_names)
        raise RuntimeError(
            f"Circular or missing dependencies detected among: {missing}"
        )

    return [name_to_dir[name] for name in sorted_names]


def _topologically_sort_images(
    unsorted_image_dirs: list[Traversable],
) -> list[Traversable]:
    """Return image_dirs sorted topologically based on 'depends_on' metadata."""
    name_to_dir, dependencies, reverse_deps = _build_dependency_graph(
        unsorted_image_dirs
    )
    return _kahn_sort(name_to_dir, dependencies, reverse_deps)


@cache
def docker_images_root() -> Traversable:
    return importlib.resources.files("resources").joinpath("docker-images")


def test_images_dir_exists() -> None:
    assert_that(docker_images_root().is_dir()).described_as(
        f"'resources/docker-images' directory not found at {docker_images_root()!r}"
    )


@pytest.mark.parametrize(
    "image_dir", image_dirs(), ids=[path.name for path in image_dirs()]
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

    ctx: AbstractContextManager[Path | Traversable]
    if info.get("extract", False):
        ctx = importlib.resources.as_file(image_dir)
    else:
        ctx = nullcontext(image_dir)

    with ctx as alias_img_dir:
        # Build the Docker image
        res1 = subprocess.run(
            ["docker", "build", "-t", image_name, str(alias_img_dir)],
            check=False,
            capture_output=True,
            text=True,
        )
        with soft_assertions():
            assert_that(res1.returncode).described_as(
                f"Return code when building {image_name} was not zero. "
                f"Stderr = {res1.stderr}"
            ).is_equal_to(0)
            assert_that(res1.stdout).described_as(
                f"Failed to build {image_name}: stdout"
            ).is_equal_to("")

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
            check=False,
            capture_output=True,
        )
        with soft_assertions():
            assert_that(res2.returncode).described_as("returncode").is_equal_to(0)
            assert_that(res2.stdout.strip()).described_as("stdout").is_equal_to(
                b"Hello"
            )
            assert_that(res2.stderr).described_as("stderr").is_equal_to(b"")


@pytest.fixture(scope="class")
def docker_oo_docker_container() -> Generator[tuple[DockerRunner, str]]:
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
    docker_oo_docker_container: tuple[DockerRunner, str],
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
    docker_oo_docker_container: tuple[DockerRunner, str],
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
    docker_oo_docker_container: tuple[DockerRunner, str],
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


def test_correct_image_order() -> None:
    assert_that([x.name for x in image_dirs()]).is_equal_to(
        ["dind-dev", "python-dev", "python-dev-loaded", "python-dev-docker-cli"]
    )
