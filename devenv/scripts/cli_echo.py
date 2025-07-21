#!/usr/bin/env python3

"""Prints to stdout a JSON snapshot of what a command-line target would "see" when
called the way this program was called: current working directory, passed arguments,
user and home directory, root/admin status, OS name, and some Python interpreter
details.

This help is included in the results if and only if "-h" or "--help" is the first
command-line argument.
"""

if __name__ == "__main__":
    import getpass
    import json
    import os
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
        "os_name": os.name,
        "python": {
            "sys.argv[0]": sys.argv[0],
            "python_executable": sys.executable,
            "python_version": sys.version,
        },
    }

    if sys.argv[1:] and sys.argv[1] in ("-h", "--help"):
        info = {"help": __doc__, **info}

    json.dump(info, sys.stdout, indent=2, ensure_ascii=True)
    print("")
