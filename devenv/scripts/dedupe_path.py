#!/usr/bin/env python3


def de_dupe(path: str, allow_relative: bool = True) -> str:
    return ":".join(
        x
        for x in {
            x: None for x in path.split(":") if allow_relative or x.startswith("/")
        }.keys()
    )


if __name__ == "__main__":
    import sys

    if not sys.argv[1:]:
        print(f"No input PATH supplied.")
        sys.exit(1)
    else:
        print(de_dupe(sys.argv[1]))
