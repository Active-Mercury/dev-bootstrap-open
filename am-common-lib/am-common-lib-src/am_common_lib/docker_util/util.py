"""Utility helpers for docker-related tests and tooling."""

from dataclasses import dataclass
import functools
from functools import cache
import re
import string
import zlib


@dataclass(frozen=True)
class ImageNames:
    """Canonical Docker image names used across tests."""

    ALPINE_LATEST: str = "alpine:latest"
    BUSYBOX_LATEST: str = "busybox:latest"
    UBUNTU_LATEST: str = "ubuntu:latest"
    PYTHON_DEV: str = "python-dev"
    PYTHON_DEV_LOADED: str = "python-dev-loaded"
    PYTHON_DEV_DOCKER_CLI: str = "python-dev-docker-cli"


DockerImageNames = ImageNames()


@dataclass(frozen=True)
class SpecialImageNames:
    """Special-case image names used in certain scenarios."""

    ALPINE_LATEST: str = "alpine:latest"
    BUSYBOX_LATEST: str = "busybox:latest"
    UBUNTU_LATEST: str = "ubuntu:latest"
    PYTHON_DEV: str = "python-dev"
    PYTHON_DEV_LOADED: str = "python-dev-loaded"


def to_base_54(token: bytes) -> str:
    """Encode ``token`` into an unambiguous base-54 string.

    :param bytes token: Arbitrary bytes to encode.
    :return: Encoded representation using a 54-character alphabet with ambiguous glyphs
        removed.
    :rtype: str
    """
    if len(token) == 0:
        return ""
    char_set = _generate_charset()
    # Convert bytes to a large integer
    num = int.from_bytes(token, "big")

    # Base conversion from integer to custom base using char_set
    if num == 0:
        return char_set[0]

    result = []
    while num > 0:
        num, rem = divmod(num, len(char_set))
        result.append(char_set[rem])

    return "".join(reversed(result))


@functools.lru_cache(maxsize=10)
def get_container_name_base(img_name: str, max_length: int | None = None) -> str:
    """Get a prefix for Docker container names based on the image name.

    This function replaces any character in the provided image name that is not
    permitted in Docker container names (i.e., characters other than letters, digits,
    underscore, period, or hyphen) with an underscore, ensuring the result is a valid
    container name base.

    :param str img_name: The original Docker image name to sanitize.
    :param int|None max_length: Optional maximum length (must be ``>=2``).
    :return: A sanitized string suitable for use as a Docker container name.
    :rtype: str
    :raises ValueError: If ``max_length`` is provided and less than 2.
    """
    sanitized_base = re.sub(r"[^A-Za-z0-9_.-]+", "_", img_name)
    if not re.match(r"^[A-Za-z0-9]", sanitized_base):
        hash_val = zlib.crc32(img_name.encode("utf-8"))
        alnum = string.ascii_letters + string.digits
        prefix_char = alnum[hash_val % len(alnum)]
        sanitized_base = prefix_char + sanitized_base
        if max_length is not None:
            if max_length < 2:
                raise ValueError("max_length must be at least 2")
            if len(sanitized_base) > max_length:
                # Keep the first char
                sanitized_base = sanitized_base[0] + sanitized_base[-(max_length - 1) :]

    return sanitized_base


@cache
def _generate_charset() -> tuple[str, ...]:
    ambiguous = {"0", "1", "i", "I", "L", "O", "l", "o"}
    return tuple(
        sorted(c for c in string.digits + string.ascii_letters if c not in ambiguous)
    )
