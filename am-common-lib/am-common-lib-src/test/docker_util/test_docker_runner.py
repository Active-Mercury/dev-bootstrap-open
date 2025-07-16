import hashlib
import os
from pathlib import Path
import posixpath
import re
import shlex
import subprocess
import tempfile
import time
from typing import BinaryIO, Generator, List

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from am_common_lib.docker_util import ImageNames
from am_common_lib.docker_util.docker_runner import DockerRunner
from am_common_lib.docker_util.docker_runner import DockerRunnerUserView


ALL_IMAGE_NAMES = [
    ImageNames.ALPINE_LATEST,
    ImageNames.BUSYBOX_LATEST,
    ImageNames.UBUNTU_LATEST,
    ImageNames.PYTHON_DEV,
    ImageNames.PYTHON_DEV_LOADED,
]


@pytest.mark.parametrize(
    "image",
    ALL_IMAGE_NAMES,
)
def test_echo_hello_in_various_images(image: str) -> None:
    container_name = None
    with DockerRunner(image) as c:
        container_name = c.container_name
        assert_that(c.img_name).is_equal_to(image)
        # Assert that the container exists
        assert_that(_run_docker_ps(container_name=container_name)).contains(
            container_name
        )
        res = c.run(["echo", "Hello"])
        with soft_assertions():
            assert_that(res.returncode).is_equal_to(0)
            assert_that(res.stdout.decode("utf-8").strip()).is_equal_to("Hello")
            assert_that(res.stderr).is_empty()

    # Assert automatic clean-up of the container
    assert_that(
        _run_docker_ps(container_name=container_name, include_all=True)
    ).does_not_contain(container_name)


@pytest.mark.parametrize(
    "version",
    [
        "5.7",
        "8.0",
    ],
)
def test_mysql_different_versions(version: str) -> None:
    image = f"mysql:{version}"
    container_name = None
    with DockerRunner(
        image,
        run_args=["-e", "MYSQL_ALLOW_EMPTY_PASSWORD=yes"],
        skip_handshake=True,
    ) as db:
        container_name = db.container_name
        # Wait up to 30 s for MySQL to become available
        for _ in range(30):
            res = db.run(["mysqladmin", "ping", "--silent"])
            if res.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("MySQL did not start in time")

        # Execute a simple version query
        result = db.run(
            ["mysql", "--silent", "--skip-column-names", "-e", "SELECT VERSION();"],
            text=True,
        )
        with soft_assertions():
            assert_that(result.returncode).described_as("returncode").is_equal_to(0)
            # Assert that the right version is returned, ignoring the patch
            assert_that(result.stdout).described_as("stdout").matches(
                re.escape(version) + r"(\.\d+)?$"
            )
            assert_that(result.stderr).described_as("stderr").is_equal_to("")
    # Assert automatic clean-up of the container
    assert_that(
        _run_docker_ps(container_name=container_name, include_all=True)
    ).does_not_contain(container_name)


def test_auto_clean_up_false() -> None:
    image = ImageNames.ALPINE_LATEST
    container_name = image

    try:
        with DockerRunner(image, auto_clean_up=False) as runner:
            container_name = runner.container_name
            assert_that(_run_docker_ps(container_name=container_name)).contains(
                container_name
            )

        assert_that(
            _run_docker_ps(container_name=container_name, include_all=True)
        ).contains(container_name)
    finally:
        # Now clean up manually
        rm = subprocess.run(
            ["docker", "rm", "-f", container_name], capture_output=True, text=True
        )
        assert_that(rm.returncode).is_equal_to(0)
        assert_that(
            _run_docker_ps(container_name=container_name, include_all=True)
        ).does_not_contain(container_name)


# ----------------------------------------------------------------------
# DockerRunner.copy_from tests
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "image",
    ALL_IMAGE_NAMES,
)
def test_file_copy_from(image: str) -> None:
    with DockerRunner(image) as c:
        default_view = c.default_view
        base_path = default_view.getcwd()
        filename = "from_container.txt"
        container_path = posixpath.join(base_path, filename)
        content = "Data from container"

        # Create the file inside the container
        res = c.run(
            [
                "sh",
                "-c",
                shlex.join(["echo", "-n", content])
                + " > "
                + shlex.quote(container_path),
            ]
        )
        with soft_assertions():
            assert_that(res.returncode).described_as("returncode").is_equal_to(0)
            assert_that(res.stdout).described_as("stdout").is_equal_to(b"")
            assert_that(res.stderr).described_as("stderr").is_equal_to(b"")

        # Copy the file out and read it into memory
        with tempfile.TemporaryDirectory() as host_dir:
            host_path = os.path.join(host_dir, filename)
            c.copy_from(container_path, host_path)

            with open(host_path, "rb") as f:
                copied = f.read()

        assert_that(copied).is_equal_to(content.encode("utf-8"))


@pytest.mark.parametrize(
    "image",
    ALL_IMAGE_NAMES,
)
def test_folder_copy_from(image: str) -> None:
    with DockerRunner(image) as c:
        default_view = c.default_view
        base_path = default_view.getcwd()
        folder_name = "test_dir"
        container_folder = posixpath.join(base_path, folder_name)

        # Make the directory in the container
        res = c.run(["mkdir", "-p", container_folder])
        assert_that(res.returncode).is_equal_to(0)

        # Create a couple of files and a nested subdir
        files = {
            "file1.txt": b"First file",
            "file2.txt": b"Second file",
            "nested/sub.txt": b"In the subdirectory",
        }
        for rel, content in files.items():
            remote_path = posixpath.join(container_folder, rel)
            # ensure parent exists
            parent = posixpath.dirname(remote_path)
            if parent:
                mkdir_res = c.run(["mkdir", "-p", parent])
                assert_that(mkdir_res.returncode).described_as(
                    f"mkdir {parent}"
                ).is_equal_to(0)
            # Write the file
            cmd = [
                "sh",
                "-c",
                shlex.join(["printf", "%s", content.decode("utf-8")])
                + " > "
                + shlex.quote(remote_path),
            ]
            write_res = c.run(cmd)
            assert_that(write_res.returncode).described_as(
                f"writing {rel}"
            ).is_equal_to(0)

        # Copy the contents out and verify that it was copied correctly
        with tempfile.TemporaryDirectory() as host_dir:
            c.copy_from(container_folder, host_dir)

            host_root = os.path.join(host_dir, folder_name)
            assert_that(os.path.isdir(host_root)).is_true()

            for rel, content in files.items():
                parts = rel.split("/")
                host_file = os.path.join(host_root, *parts)
                assert_that(os.path.isfile(host_file)).described_as(
                    f"{rel} exists"
                ).is_true()
                with open(host_file, "rb") as f:
                    data = f.read()
                assert_that(data).described_as(f"{rel} content").is_equal_to(content)


@pytest.mark.parametrize("image", ALL_IMAGE_NAMES)
def test_copy_from_nonexistent(image: str) -> None:
    with DockerRunner(image) as c:
        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "missing.txt")
            with pytest.raises(subprocess.CalledProcessError):
                c.copy_from("/no/such/path.txt", dest)


# ----------------------------------------------------------------------
# DockerRunner.copy_to tests
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "image,relative_src",
    [
        pytest.param(
            image,
            relative_src,
            id=f"{image}; relative_src={relative_src}",
        )
        for image in ALL_IMAGE_NAMES
        for relative_src in [False, True]
    ],
)
def test_copy_to_single_file_source_paths(image: str, relative_src: str) -> None:
    with DockerRunner(image) as c:
        base_path = c.default_view.getcwd()
        content = b"hello container"
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, "src.txt")
            with open(src_file, "wb") as f:
                f.write(content)
            old_cwd = os.getcwd()
            try:
                if relative_src:
                    os.chdir(tmpdir)
                    src = "src.txt"
                else:
                    src = src_file
                dest = posixpath.join(base_path, "copied.txt")
                res = c.copy_to(src, dest)
                with soft_assertions():
                    assert_that(res.returncode).described_as("returncode").is_equal_to(
                        0
                    )
                    assert_that(res.stdout).described_as("stdout").is_equal_to("")
                    assert_that(res.stderr).described_as("stderr").is_equal_to("")
            finally:
                os.chdir(old_cwd)

            res = c.run(["cat", dest], text=True, check=True)
            with soft_assertions():
                assert_that(res.returncode).described_as("returncode").is_equal_to(0)
                assert_that(res.stdout).described_as("stdout").is_equal_to(
                    content.decode("utf-8")
                )
                assert_that(res.stderr).described_as("stderr").is_equal_to("")


@pytest.mark.parametrize(
    "image,relative_src",
    [
        pytest.param(
            image,
            relative_src,
            id=f"{image}; relative_src={relative_src}",
        )
        for image in ALL_IMAGE_NAMES
        for relative_src in [False, True]
    ],
)
def test_copy_to_directory_source_paths(image: str, relative_src: str) -> None:
    with DockerRunner(image) as c:
        base_path = c.default_view.getcwd()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir_name = "src_dir"
            host_src = os.path.join(tmpdir, src_dir_name)
            files = {
                "file1.txt": b"First file",
                "nested/sub.txt": b"Nested file",
            }
            # Create files on host
            for rel, content in files.items():
                host_file = os.path.join(host_src, rel)
                os.makedirs(os.path.dirname(host_file), exist_ok=True)
                with open(host_file, "wb") as f:
                    f.write(content)

            # Decide whether to use a relative or absolute path
            old_cwd = os.getcwd()
            try:
                if relative_src:
                    os.chdir(tmpdir)
                    src = src_dir_name
                else:
                    src = host_src

                dest = posixpath.join(base_path, "copied_dir")
                res = c.copy_to(src, dest)

                # copy_to should succeed with no output
                with soft_assertions():
                    assert_that(res.returncode).described_as("returncode").is_equal_to(
                        0
                    )
                    assert_that(res.stdout).described_as("stdout").is_equal_to("")
                    assert_that(res.stderr).described_as("stderr").is_equal_to("")
            finally:
                os.chdir(old_cwd)

        # Now verify inside the container that each file exists and has the right contents
        for rel, content in files.items():
            remote_path = posixpath.join(dest, rel)
            res = c.run(["cat", remote_path], text=True, check=True)
            with soft_assertions():
                assert_that(res.returncode).described_as(
                    f"{rel} returncode"
                ).is_equal_to(0)
                assert_that(res.stdout).described_as(f"{rel} stdout").is_equal_to(
                    content.decode("utf-8")
                )
                assert_that(res.stderr).described_as(f"{rel} stderr").is_empty()


@pytest.mark.parametrize("image", ALL_IMAGE_NAMES)
def test_copy_to_nonexistent_source_raises(image: str) -> None:
    with DockerRunner(image) as c:
        with pytest.raises(subprocess.CalledProcessError):
            c.copy_to("no_such_src.txt", "/")


# ----------------------------------------------------------------------
# Tests for DockerRunner.open
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "image,workdir",
    [
        pytest.param(image, workdir, id=f"{image}; workdir={workdir}")
        for image in ALL_IMAGE_NAMES
        for workdir in (None, "test_open_wd")
    ],
)
def test_open_read_nonexistent_raises(image: str, workdir: str | None) -> None:
    with DockerRunner(image) as c:
        if workdir:
            c.run(["mkdir", "-p", workdir], check=True)

        with pytest.raises(FileNotFoundError):
            # the context‐manager __enter__ will error if the file doesn't exist
            with c.open("no_such_file.txt", mode="rb", workdir=workdir):
                pass


@pytest.mark.parametrize(
    "image,workdir_flag",
    [
        pytest.param(img, wd, id=f"{img}; workdir={wd}")
        for img in ALL_IMAGE_NAMES
        for wd in (True, False)
    ],
)
def test_open_write_and_read(image: str, workdir_flag: bool) -> None:
    content1 = b"hello via open"
    content2 = b"; goodbye"
    subdir1 = "foo"
    subdir2 = "bar"
    filename = "testfile.txt"

    with DockerRunner(image) as c:
        base_path = c.default_view.getcwd()
        full_dir = posixpath.join(base_path, subdir1, subdir2)
        c.run(["mkdir", "-p", full_dir], check=True)

        def assert_writing(wf: BinaryIO) -> None:
            assert_that(wf.isatty()).is_false()
            assert_that(wf.mode).is_equal_to("wb")
            assert_that(wf.writable()).is_true()
            assert_that(wf.readable()).is_false()
            assert_that(wf.seekable()).is_false()
            assert_that(wf.write(content1)).is_equal_to(len(content1))
            assert_that(wf.write(content2)).is_equal_to(len(content2))

        def assert_reading(rf: BinaryIO) -> None:
            assert_that(rf.isatty()).is_false()
            assert_that(rf.mode).is_equal_to("rb")
            assert_that(rf.writable()).is_false()
            assert_that(rf.readable()).is_true()
            assert_that(rf.seekable()).is_false()
            part1 = rf.read(5)
            assert_that(part1).is_equal_to(content1[:5])
            part2 = rf.read()
            assert_that(part1 + part2).is_equal_to(content1 + content2)

        if workdir_flag:
            # CASE A: supply workdir + relative path
            workdir = posixpath.join(base_path, subdir1)
            rel_path = f"{subdir2}/{filename}"

            with c.open(rel_path, mode="wb", workdir=workdir) as f:
                assert_writing(f)

            expected = posixpath.join(full_dir, filename)
            c.run(["test", "-f", expected], check=True)

            with c.open(rel_path, mode="rb", workdir=workdir) as f:
                assert_reading(f)
        else:
            # CASE B: no workdir, absolute path
            abs_path = posixpath.join(full_dir, filename)

            with c.open(abs_path, mode="wb") as f:
                assert_writing(f)

            c.run(["test", "-f", abs_path], check=True)
            with c.open(abs_path, mode="rb") as f:
                assert_reading(f)


# ----------------------------------------------------------------------
# Tests for DockerRunner.makedirs
# ----------------------------------------------------------------------


@pytest.mark.parametrize("image", ALL_IMAGE_NAMES)
def test_makedirs_creates_nested_dirs(image: str) -> None:
    with DockerRunner(image) as c:
        base = c.default_view.getcwd()
        path = posixpath.join(base, "foo", "bar", "baz")
        c.makedirs(path)
        # Verify the deepest directory was created
        c.run(["test", "-d", path], check=True)


@pytest.mark.parametrize("image", ALL_IMAGE_NAMES)
def test_makedirs_exist_ok_false_raises(image: str) -> None:
    with DockerRunner(image) as c:
        base = c.default_view.getcwd()
        dup = posixpath.join(base, "dupdir")
        # First creation succeeds
        c.makedirs(dup)
        # Second without -p should fail
        with pytest.raises(subprocess.CalledProcessError):
            c.makedirs(dup, exist_ok=False)


@pytest.mark.parametrize("image", ALL_IMAGE_NAMES)
def test_makedirs_with_workdir_relative(image: str) -> None:
    with DockerRunner(image) as c:
        base = c.default_view.getcwd()
        # Create a nested path relative to workdir
        rel = "rel1/rel2"
        c.makedirs(rel, workdir=base)
        full = posixpath.join(base, rel)
        c.run(["test", "-d", full], check=True)


@pytest.mark.parametrize("image", [ImageNames.PYTHON_DEV, ImageNames.PYTHON_DEV_LOADED])
@pytest.mark.parametrize("user", ["basicuser", "superuser"])
def test_makedirs_with_user(image: str, user: str) -> None:
    with DockerRunner(image) as c:
        base_path = Path("/", "home", user)
        target1 = (base_path / "new-directory").as_posix()
        c.makedirs(target1, user=user)
        c.run(["test", "-d", target1], check=True)
        target2 = (base_path / "foo" / "bar").as_posix()
        c.makedirs(target2, user=user)
        c.run(["test", "-d", target2], check=True)

        # Verify ownership
        res = c.run(
            ["stat", "-c", "%U", (base_path / "foo").as_posix()], text=True, check=True
        )
        assert_that(res.stdout.strip()).is_equal_to(user)
        res = c.run(
            ["stat", "-c", "%U", (base_path / "foo" / "bar").as_posix()],
            text=True,
            check=True,
        )
        assert_that(res.stdout.strip()).is_equal_to(user)


# ======================================================================
# Tests for DockerRunnerUserView
# ======================================================================


@pytest.fixture(scope="function")
def user_view_rw_operations() -> Generator[DockerRunnerUserView, None, None]:
    with DockerRunner(ImageNames.PYTHON_DEV) as base:
        yield base.use_as("basicuser")


@pytest.fixture(scope="class")
def user_view_ro_operations() -> Generator[DockerRunnerUserView, None, None]:
    with DockerRunner(ImageNames.PYTHON_DEV) as base:
        yield base.use_as("basicuser")


def test_use_as_wrapper_respects_user_and_workdir(
    user_view_ro_operations: DockerRunnerUserView,
) -> None:
    user_view = user_view_ro_operations
    assert_that(user_view.getcwd()).is_equal_to("/home/basicuser")
    assert_that(user_view.username).is_equal_to("basicuser")
    r = user_view.run(["id", "-un"], text=True)
    with soft_assertions():
        assert_that(r.returncode).described_as("returncode").is_equal_to(0)
        assert_that(r.stdout).described_as("stdout").is_equal_to("basicuser\n")
        assert_that(r.stderr).described_as("stderr").is_equal_to("")


def test_chdir_changes_cwd(user_view_rw_operations: DockerRunnerUserView) -> None:
    user_view_rw_operations.chdir("/tmp")
    assert_that(user_view_rw_operations.getcwd()).is_equal_to("/tmp")


def test_copy_to_preserves_ownership(
    user_view_rw_operations: DockerRunnerUserView,
) -> None:
    user_view = user_view_rw_operations
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        file_on_host = tmp_path / "owned.txt"
        file_on_host.write_text("Check me")

        dest_path = "/home/basicuser/owned.txt"
        user_view.copy_to(file_on_host, dest_path)

        result = user_view.run(["ls", "-l", dest_path], text=True)
        assert_that(result.stdout).contains("basicuser", "owned.txt")


def test_user_view_copy_to_directory(
    user_view_rw_operations: DockerRunnerUserView,
) -> None:
    user_view = user_view_rw_operations
    # Prepare a host directory with some files
    with tempfile.TemporaryDirectory() as tmpdir:
        host_src = Path(tmpdir) / "src_dir"
        files = {
            "a.txt": b"First",
            "sub/b.txt": b"Second",
        }
        for rel, content in files.items():
            path = host_src / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        # Copy the directory into the container
        dest = posixpath.join(user_view.getcwd(), "dest_dir")
        user_view.copy_to(host_src, dest)

    # Verify each file is present in the container with correct contents
    for rel, content in files.items():
        remote = posixpath.join(dest, rel)
        res = user_view.run(["cat", remote], text=True, check=True)
        with soft_assertions():
            assert_that(res.returncode).is_equal_to(0)
            assert_that(res.stdout).is_equal_to(content.decode("utf-8"))
            assert_that(res.stderr).is_equal_to("")


def test_user_view_copy_to_directory_preserves_ownership(
    user_view_rw_operations: DockerRunnerUserView,
) -> None:
    user_view = user_view_rw_operations
    username = user_view.username  # e.g. "basicuser"

    # Prepare a small nested host directory
    with tempfile.TemporaryDirectory() as tmpdir:
        host_src = Path(tmpdir) / "nested_src"
        files = {
            "top.txt": b"top level",
            "subdir/mid.txt": b"in subdir",
            "subdir/deeper/deep.txt": b"deep level",
        }
        for rel, content in files.items():
            p = host_src / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)

        # Copy into container
        dest = posixpath.join(user_view.getcwd(), "owned_dest")
        user_view.copy_to(host_src, dest)

    to_check = [
        "",
        "subdir",
        "subdir/deeper",
        "top.txt",
        "subdir/mid.txt",
        "subdir/deeper/deep.txt",
    ]
    for rel in to_check:
        path = posixpath.join(dest, rel) if rel else dest
        result = user_view.run(
            ["stat", "-c", "%U", path],
            text=True,
            check=True,
        )
        # stat -c %U prints the owner username
        assert_that(result.stdout.strip()).is_equal_to(username)


@pytest.mark.parametrize("image", ALL_IMAGE_NAMES)
def test_root_view_copy_to_directory_preserves_ownership(image: str) -> None:
    with DockerRunner(image) as runner:
        # Create a root user view with workdir set to /root
        root_view = runner.use_as("root", workdir="/root")
        username = root_view.username
        assert_that(username).is_equal_to("root")

        # Create a temporary directory on host with nested structure
        with tempfile.TemporaryDirectory() as tmpdir:
            host_src = Path(tmpdir) / "nested_src"
            files = {
                "top.txt": b"top level",
                "subdir/mid.txt": b"in subdir",
                "subdir/deeper/deep.txt": b"deep level",
            }

            # Create files in temporary directory
            for rel, content in files.items():
                p = host_src / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(content)

            # Copy into container using root view
            dest = posixpath.join(root_view.getcwd(), "owned_dest")
            root_view.copy_to(host_src, dest)

        # Verify ownership of all paths
        paths_to_check = [
            "",
            "subdir",
            "subdir/deeper",
            "top.txt",
            "subdir/mid.txt",
            "subdir/deeper/deep.txt",
        ]

        for rel in paths_to_check:
            path = posixpath.join(dest, rel) if rel else dest
            result = root_view.run(
                ["stat", "-c", "%U", path],
                text=True,
                check=True,
            )
            assert_that(result.stdout.strip()).is_equal_to(username)


def test_user_view_write_file_and_file_exists(
    user_view_rw_operations: DockerRunnerUserView,
) -> None:
    user_view = user_view_rw_operations
    filename = "written_via_api.txt"
    contents = b"WriteFile works!"

    # Write and assert return value
    count = user_view.write_file(filename, contents)
    assert_that(count).is_equal_to(len(contents))

    # Confirm the file exists inside the container
    abs_path = posixpath.join(user_view.getcwd(), filename)
    user_view.run(["test", "-f", abs_path], check=True)


def test_user_view_read_file_returns_expected_bytes(
    user_view_rw_operations: DockerRunnerUserView,
) -> None:
    user_view = user_view_rw_operations
    filename = "roundtrip.txt"
    contents = b"Round-trip through read_file"

    # First, write via the API
    user_view.write_file(filename, contents)

    # Then, read back via read_file
    read_back = user_view.read_file(filename)
    assert_that(read_back).is_equal_to(contents)


# ======================================================================
# Helpers
# ======================================================================


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_docker_ps(*, container_name: str, include_all: bool = False) -> List[str]:
    """Run `docker ps`, optionally including stopped containers, filtered by name, and
    return a list of container names that match."""
    cmd = ["docker", "ps"]
    if include_all:
        cmd.append("-a")
    cmd += ["--filter", f"name={container_name}", "--format", "{{.Names}}"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return [line for line in result.stdout.strip().splitlines() if line]
