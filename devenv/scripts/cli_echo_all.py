#!/usr/bin/env python3

"""Prints to stdout a JSON snapshot of what a command-line target would "see" when
called the way this program was called: current working directory, passed arguments,
user and home directory, root/admin status, process id, OS name, Python interpreter
details, all environment variables, and some platform details.

This help is included in the results if and only if "-h" or "--help" is the first
command-line argument.
"""

if __name__ == "__main__":
    import getpass
    import json
    import os
    import platform
    import sys
    from typing import Optional

    def has_root_privileges() -> Optional[bool]:
        import os

        try:
            if os.name == "nt":  # Windows
                import ctypes

                try:
                    return ctypes.windll.shell32.IsUserAnAdmin() != 0
                except Exception:
                    return None
            else:  # Unix/Linux/Mac
                return os.geteuid() == 0
        except Exception:
            return None

    info = {
        "cwd": os.getcwd(),
        "args": sys.argv[1:],
        "user": getpass.getuser(),
        "user_home_dir": os.path.expanduser("~"),
        "is_root": has_root_privileges(),
        "process_id": os.getpid(),
        "os_name": os.name,
        "python": {
            "sys.argv[0]": sys.argv[0],
            "python_executable": sys.executable,
            "python_version": sys.version,
        },
        "environment_variables": dict(os.environ),
        "platform": {
            "platform": platform.platform(),
            "python_version_tuple": platform.python_version_tuple(),
            "architecture": platform.architecture(),
            "machine": platform.machine(),
            "node": platform.node(),
            "processor": platform.processor(),
            "release": platform.release(),
            "system": platform.system(),
            "version": platform.version(),
        },
    }

    if sys.argv[1:] and sys.argv[1] in ("-h", "--help"):
        info = {"help": __doc__, **info}

    json.dump(info, sys.stdout, indent=2, ensure_ascii=True)
    print("")
