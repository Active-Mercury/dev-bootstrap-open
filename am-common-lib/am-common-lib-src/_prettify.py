import os
import shlex
import subprocess


def main() -> None:
    this_file = __file__
    this_dir = os.path.dirname(os.path.abspath(this_file))

    cwd = os.getcwd()
    rel_path = os.path.relpath(cwd, this_dir).replace(os.path.sep, "/")
    container_repo = "/home/basicuser/prettier-formatter/git-repo"
    container_workdir = f"{container_repo}/{rel_path}"

    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{this_dir}:{container_repo}",
        "-w",
        container_workdir,
        "python-dev-loaded",
        "npx",
        "prettier",
        ".",
        "--write",
    ]

    print(f"Running: {shlex.join(cmd)}")
    exit(subprocess.run(cmd, check=False).returncode)


if __name__ == "__main__":
    main()
