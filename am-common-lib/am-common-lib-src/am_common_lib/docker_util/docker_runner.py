"""High-level API over docker CLI for running commands and file operations.

Provides context-managed access to a long-lived container and user-scoped views with
helpers for copying and reading/writing files.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache
from functools import cached_property
import io
import os
from pathlib import Path
import subprocess
from subprocess import CompletedProcess
import tarfile
from types import TracebackType
from typing import Any, BinaryIO, Literal
import uuid

from .util import get_container_name_base
from .util import to_base_54


class DockerRunner:
    """Manage a long-running Docker container for ad-hoc execution.

    Provides convenience methods to execute commands, copy files, and open file-like
    streams within the container.

    :param str img_name: Image name to run.
    :param bool auto_clean_up: If ``True``, remove the container on exit.
    :param Sequence[str]|None run_args: Extra flags to pass to ``docker run``.
    :param bool skip_handshake: Skip initial echo handshake validation.
    """

    def __init__(
        self,
        img_name: str,
        auto_clean_up: bool = True,
        *,
        run_args: Sequence[str] | None = None,
        skip_handshake: bool = False,
    ) -> None:
        self._run_args: list[str] = list(run_args) if run_args is not None else []
        self._img_name = img_name
        base_img_name = get_container_name_base(img_name, max_length=39)
        self._uniq_name = f"{base_img_name}_{to_base_54(uuid.uuid4().bytes)}"
        self._auto_clean_up = auto_clean_up
        self._skip_handshake = skip_handshake

    def __enter__(self) -> DockerRunner:
        extra_args = ["--rm"] if self._auto_clean_up else []
        extra_args += self._run_args

        command = [
            "docker",
            "run",
            "-i",
            *extra_args,
            "--name",
            self._uniq_name,
            self._img_name,
        ]

        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert self._process.stdin and self._process.stdout, (
                "subprocess.PIPE was specified for both stdout and stdin, "
                "so they should have been not None"
            )

            if not self._skip_handshake:
                self._process.stdin.write("echo Hi\n")
                self._process.stdin.flush()
                output = self._process.stdout.readline().strip()
                if output != "Hi":
                    raise Exception(
                        f"Initialization failed: expected 'Hi', but got '{output}'"
                    )
        except Exception:
            # If there was an exception in this section, the __exit__ will not run,
            # and the container is probably unusable, so remove it.
            self._force_remove_container()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        assert self._process.stdin is not None, (
            "Expecting stdin and stdout to be pipes: the docker process is always "
            "launched with pipes for stdin and stdout."
        )
        if self._process:
            self._process.stdin.write("exit 0\n")
            self._process.stdin.flush()
            try:
                self._process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                if self._auto_clean_up:
                    # Just in case killing the "docker run" process was not enough
                    self._force_remove_container()
        return False

    def _force_remove_container(self) -> None:
        """Try to remove the container forcibly on a fire-and-forget basis."""
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def use_as(self, username: str, workdir: str | None = None) -> DockerRunnerUserView:
        """Return a user-scoped view on this runner.

        :param str username: Username inside the container.
        :param str|None workdir: Optional working directory to validate and adopt.
        :return: A user-scoped view bound to the given ``username``.
        :rtype: DockerRunnerUserView
        """

        return DockerRunnerUserView(self, username, workdir)

    @cached_property
    def default_view(self) -> DockerRunnerUserView:
        """Return a user-scoped view for the container's default user.

        :return: A user-scoped view bound to the default container user.
        :rtype: DockerRunnerUserView
        """
        default_user = self.run(["id", "-un"], text=True).stdout.strip()
        workdir = self.run(["pwd"], text=True).stdout.strip()
        return DockerRunnerUserView(self, default_user, workdir)

    def run(
        self,
        cmd: Sequence[str],
        *,
        exec_args: Sequence[str] | None = None,
        user: str | None = None,
        workdir: str | None = None,
        text: bool = False,
        capture_output: bool = True,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[Any]:
        """Execute a command in the running container.

        :param Sequence[str] cmd: Command (and args) to execute.
        :param Sequence[str]|None exec_args: Extra flags for ``docker exec`` (e.g.,
            ``["-i", "-t"]``).
        :param str|None user: User to run as (equivalent to ``-u``).
        :param str|None workdir: Working directory (equivalent to ``-w``).
        :param bool text: Open pipes in text mode (alias for ``text=``).
        :param bool capture_output: Forwarded to ``subprocess.run``; defaults to
            ``True``.
        :param Any **kwargs: Additional ``subprocess.run`` keyword arguments (e.g.,
            ``check=True``).
        :return: Completed process result.
        :rtype: subprocess.CompletedProcess[Any]
        """
        # Pull out any capture_output/text overrides from kwargs
        # (so they don't get passed twice)
        # (we already have them as named parameters)
        # build the docker command
        docker_cmd = ["docker", "exec"]
        if exec_args:
            docker_cmd.extend(exec_args)
        if user:
            docker_cmd.extend(["-u", user])
        if workdir:
            docker_cmd.extend(["-w", workdir])

        docker_cmd.append(self._uniq_name)
        docker_cmd.extend(cmd)

        return subprocess.run(
            docker_cmd,
            capture_output=capture_output,
            text=text,
            **kwargs,
        )

    @cached_property
    def container_name(self) -> str:
        """Get the underlying container name.

        :return: The unique Docker container name for this runner instance.
        :rtype: str
        """
        return self._uniq_name

    @cached_property
    def img_name(self) -> str:
        """Get the image name this runner was created with.

        :return: Original Docker image name.
        :rtype: str
        """
        return self._img_name

    def copy_from(
        self, src_path: str, dest_path: str
    ) -> subprocess.CompletedProcess[str]:
        """Copy from the container using ``docker cp``.

        :param str src_path: Path inside the container to copy from.
        :param str dest_path: Path on the host to copy to.
        :return: Completed process result.
        :rtype: subprocess.CompletedProcess[str]
        """
        cp_command = ["docker", "cp", f"{self._uniq_name}:{src_path}", dest_path]
        return subprocess.run(cp_command, capture_output=True, check=True, text=True)

    def copy_to(
        self, src_path: str | Path | Sequence[str | Path], dest_path: str
    ) -> subprocess.CompletedProcess[str]:
        """Copy a file or folder into the container via ``docker cp``.

        :param str|Path|Sequence[str|Path] src_path: Local source path(s).
        :param str dest_path: Destination path inside the container.
        :return: Completed process result.
        :rtype: subprocess.CompletedProcess[str]
        """
        if isinstance(src_path, (str, Path)):
            sources = [str(src_path)]
        else:
            sources = [str(p) for p in src_path]

        cmd = ["docker", "cp"]
        cmd.extend(sources)
        cmd.append(f"{self.container_name}:{dest_path}")

        return subprocess.run(cmd, capture_output=True, text=True, check=True)

    def open(
        self,
        path: str,
        mode: str = "rb",
        user: str | None = None,
        workdir: str | None = None,
    ) -> BinaryIO:
        """Open a container file for binary read or write.

        :param path: Absolute or relative file path inside the container.
        :type path: str
        :param mode: Either ``"rb"`` or ``"wb"``.
        :type mode: str
        :param str|None user: Username to use for the operation.
        :param str|None workdir: Working directory for relative paths.
        :return: A binary file-like object backed by docker exec.
        :rtype: BinaryIO
        :raises ValueError: If an unsupported mode is provided.
        """
        if mode not in {"rb", "wb"}:
            raise ValueError(f"Unsupported mode: {mode!r}")

        # If workdir is set and path is relative, prepend it
        if workdir and not path.startswith("/"):
            path = f"{workdir.rstrip('/')}/{path.lstrip('/')}"

        return _DockerFileIO(self, path, mode, user=user, cwd=workdir)

    def makedirs(
        self,
        path: str,
        *,
        user: str | None = None,
        exist_ok: bool = True,
        workdir: str | None = None,
    ) -> None:
        """Recursively create directories inside the container.

        Roughly mirrors ``os.makedirs`` semantics.

        :param str path: Directory path to create.
        :param str|None user: Username for the operation.
        :param bool exist_ok: Do not error if the directory exists.
        :param str|None workdir: Working directory for relative paths.
        """
        mkdir_cmd = ["mkdir"]
        if exist_ok:
            mkdir_cmd.append("-p")
        mkdir_cmd.append(path)
        self.run(mkdir_cmd, user=user, workdir=workdir, check=True)

    @cache
    def get_home_dir(self, username: str) -> str:
        """Return the home directory for ``username`` inside the container.

        :param str username: The container username.
        :return: Absolute path to the user's home directory.
        :rtype: str
        """
        res: CompletedProcess[str] = self.run(
            ["sh", "-c", "echo ~"], user=username, text=True, check=True
        )
        return res.stdout.strip()


class DockerRunnerUserView:
    """Represent a logged-in user's session inside a container.

    Keeps track of the current working directory and provides helpers that run
    commands/files as the associated user.

    :param DockerRunner base: The DockerRunner instance this view is based on.
    :param str username: The username to operate as within the container.
    :param workdir: The working directory for operations (defaults to user's home).
    :type workdir: str | None
    """

    def __init__(self, base: DockerRunner, username: str, workdir: str | None = None):
        self._base = base
        self._username = username
        self._cwd: str

        # Validate user and get working directory
        if workdir is None:
            self._cwd = self._base.get_home_dir(username)
        else:
            result = self._base.run(
                ["pwd"], user=username, workdir=workdir, text=True, check=True
            )
            self._cwd = result.stdout.strip()

    @cached_property
    def parent_runner(self) -> DockerRunner:
        """Get the parent runner for which this is a user view.

        :return: The parent :class:`DockerRunner` instance.
        :rtype: DockerRunner
        """
        return self._base

    @cached_property
    def username(self) -> str:
        """Get the username associated with this view.

        :return: The username used for operations in this view.
        :rtype: str
        """
        return self._username

    @cache
    def home(self) -> str:
        """Cached home directory for this user view.

        :return: Home directory path inside the container.
        :rtype: str
        """
        return self.parent_runner.get_home_dir(self.username)

    def run(
        self,
        cmd: Sequence[str],
        *,
        exec_args: Sequence[str] | None = None,
        workdir: str | None = None,
        text: bool = False,
        capture_output: bool = True,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[Any]:
        """Execute a command in the container as this view's user.

        :param Sequence[str] cmd: Command (and args) to execute.
        :param Sequence[str]|None exec_args: Extra flags for ``docker exec``
            (e.g., ``["-i", "-t"]``).
        :param str|None workdir: If provided, overrides this view's cwd; otherwise
            uses :py:meth:`getcwd`.
        :param bool text: Open pipes in text mode (alias for ``text=``).
        :param bool capture_output: Value passed to ``subprocess.run``. Defaults to
            ``True`` (unlike the default in ``subprocess.run`` which is ``False``).
        :param Any **kwargs: Any other ``subprocess.run`` kwargs (e.g., ``check=True``).
        :return: Completed process result.
        :rtype: subprocess.CompletedProcess[Any]
        """
        actual_workdir = workdir if workdir is not None else self._cwd
        return self._base.run(
            cmd,
            exec_args=exec_args,
            user=self.username,
            workdir=actual_workdir,
            text=text,
            capture_output=capture_output,
            **kwargs,
        )

    def open(self, path: str, mode: str = "rb") -> BinaryIO:
        """Open a file in the container for reading or writing.

        :param str path: File path to open (relative to current working directory).
        :param str mode: File mode (``'rb'`` for reading, ``'wb'`` for writing).
        :return: File-like object for container file access.
        :rtype: BinaryIO
        """
        return self._base.open(path, mode=mode, user=self.username, workdir=self._cwd)

    def copy_to(
        self,
        src_path: str | Path,
        dest_path: str,
        makedirs: bool = True,
    ) -> None:
        """Copy local files/directories into the container as the current user. This
        method does not use `docker cp`. Instead, it simulates the logged-in user
        downloading data into the container:

        - For directories: Streams content as a tarball and unpacks in container
        - For files: Writes directly through container file API

        Preserves user ownership and permissions.

        :param src_path: Local source file/directory path.
        :type src_path: str | Path
        :param str dest_path: Container destination path.
        :param bool makedirs: Create parent directories if missing (default
            ``True``).
        :raises FileNotFoundError: If source path doesn't exist
        :raises RuntimeError: If directory extraction fails
        """
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"Source path '{src}' does not exist")

        if src.is_dir():
            # Ensure the directory exists in the container
            self.run(["mkdir", "-p", dest_path], check=True)

            def _strip_user_group(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
                tarinfo.uid = 0
                tarinfo.gid = 0
                tarinfo.uname = ""
                tarinfo.gname = ""
                return tarinfo

            # Stream a gzipped tarball into that dir and unpack it
            proc = subprocess.Popen(
                [
                    "docker",
                    "exec",
                    "-i",
                    "-u",
                    self.username,
                    "-w",
                    self._cwd,
                    self._base.container_name,
                    "tar",
                    "-C",
                    dest_path,
                    "-xzf",
                    "-",
                ],
                stdin=subprocess.PIPE,
            )
            with tarfile.open(fileobj=proc.stdin, mode="w|gz") as tar:
                for item in src.iterdir():
                    tar.add(item, arcname=item.name, filter=_strip_user_group)
            assert proc.stdin is not None, "proc was opened with stdin=subprocess.PIPE"
            proc.stdin.close()
            ret = proc.wait()
            if ret != 0:
                raise RuntimeError(
                    f"Failed to extract directory '{src_path}' "
                    f"into container (exit code {ret})."
                )
        else:
            if makedirs:
                parent = os.path.dirname(dest_path) or "."
                self.makedirs(parent)

            with open(src, "rb") as lf, self.open(dest_path, "wb") as wf:
                for chunk in iter(lambda: lf.read(8192), b""):
                    wf.write(chunk)

    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """Create directories in the container as the current user.

        :param str path: Directory path to create.
        :param bool exist_ok: Don't raise error if directory exists (default ``True``).
        """
        mkdir_cmd = ["mkdir"]
        if exist_ok:
            mkdir_cmd.append("-p")
        mkdir_cmd.append(path)
        self.run(mkdir_cmd, check=True)

    def getcwd(self) -> str:
        """Get the current working directory for this user view.

        :return: Absolute path of current working directory.
        :rtype: str
        """
        return self._cwd

    def chdir(self, new_dir: str) -> None:
        """Change the current working directory for this user view.

        :param str new_dir: New working directory path.
        """
        result = self.run(["pwd"], workdir=new_dir, text=True, check=True)
        self._cwd = result.stdout.strip()

    def write_file(self, file_name: str, contents: bytes) -> int:
        """Write content to a file in the container as the current user.

        :param str file_name: Target filename (relative to working directory).
        :param bytes contents: Binary content to write.
        :return: Number of bytes written.
        :rtype: int
        """
        with self.open(file_name, "wb") as wf:
            return wf.write(contents)

    def read_file(self, file_name: str) -> bytes:
        """Read content from a file in the container as the current user.

        :param str file_name: Source filename (relative to working directory).
        :return: Binary content of the file.
        :rtype: bytes
        """
        with self.open(file_name, "rb") as f:
            return f.read()


class _DockerFileIO(io.RawIOBase, BinaryIO):
    def __init__(
        self,
        runner: DockerRunner,
        path: str,
        mode: str,
        user: str | None = None,
        cwd: str | None = None,
    ) -> None:
        self._runner = runner
        self.path = path
        self._mode = mode
        self.user = user
        self._cwd = cwd
        # tell mypy this will later be a Popen[bytes]
        self._proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> _DockerFileIO:
        base_cmd = ["docker", "exec", "-i"]
        if self.user:
            base_cmd.extend(["-u", self.user])
        if self._cwd:
            base_cmd.extend(["-w", self._cwd])
        base_cmd.append(self._runner.container_name)

        if self._mode == "wb":
            self._proc = subprocess.Popen(
                base_cmd + ["tee", self.path],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        elif self._mode == "rb":
            # Check for existence before launching cat
            r = self._runner.run(["test", "-f", self.path])
            if r.returncode != 0:
                raise FileNotFoundError(f"No such file or directory: '{self.path}'")
            self._proc = subprocess.Popen(
                base_cmd + ["cat", self.path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # We know __enter__ must have been called, so _proc is set
        assert self._proc is not None, "FileIO must be open before exiting"

        if self._mode == "wb":
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.wait()
        elif self._mode == "rb":
            if self._proc.stdout:
                self._proc.stdout.close()
            self._proc.wait()

    @property
    def mode(self) -> str:
        return self._mode

    def readable(self) -> bool:
        return self._mode == "rb"

    def writable(self) -> bool:
        return self._mode == "wb"

    def write(self, data: Any) -> int:
        if self._mode != "wb" or not self._proc or not self._proc.stdin:
            raise ValueError("File not open for writing.")
        self._proc.stdin.write(data)
        self._proc.stdin.flush()
        return len(data)

    def read(self, data_size: int | None = None) -> bytes:
        if self._mode != "rb" or not self._proc or not self._proc.stdout:
            raise ValueError("File not open for reading.")

        if data_size is None:
            # This implies: read all, then check process result
            data = self._proc.stdout.read()
            self._proc.stdout.close()
            self._proc.wait()

            if self._proc.returncode != 0:
                stderr = (
                    self._proc.stderr.read().decode().strip()
                    if self._proc.stderr
                    else ""
                )
                raise FileNotFoundError(
                    f"Failed to read file '{self.path}' in container. "
                    f"Return code: {self._proc.returncode}. Stderr: {stderr}"
                )

            return data

        # data_size is set -- read a chunk and assume caller will continue reading
        try:
            return self._proc.stdout.read(data_size)
        except Exception as e:
            raise OSError(f"Error reading from container file '{self.path}': {e}")
