import importlib.resources
from typing import BinaryIO, TextIO


def open_resource_text(
    package: str, resource: str, *, encoding: str = "utf-8", errors: str = "strict"
) -> TextIO:
    """Open a text resource file from the specified package.

    :param package: The package or module name containing the resource.
    :param resource: The name of the resource file to open.
    :param encoding: The text encoding to use (default is "utf-8").
    :param errors: The encoding error handling scheme (default is "strict").
    :return: A text IO stream for reading the resource.
    :rtype: TextIO
    """
    return importlib.resources.open_text(
        package, resource, encoding=encoding, errors=errors
    )


def open_resource_binary(package: str, resource: str) -> BinaryIO:
    """Open a binary resource file from the specified package.

    :param package: The package or module name containing the resource.
    :param resource: The name of the resource file to open.
    :return: A binary IO stream for reading the resource.
    :rtype: BinaryIO
    """
    return importlib.resources.open_binary(package, resource)


def read_resource_text(package: str, resource: str, *, encoding: str = "utf-8") -> str:
    """Read the contents of a text resource file from the specified package.

    :param package: The package or module name containing the resource.
    :param resource: The name of the resource file to read.
    :param encoding: The text encoding to use when reading (default is "utf-8").
    :return: The full contents of the resource as a string.
    :rtype: str
    """
    return importlib.resources.files(package).joinpath(resource).read_text(encoding)


def read_resource_bytes(package: str, resource: str) -> bytes:
    """Read the contents of a binary resource file from the specified package.

    :param package: The package or module name containing the resource.
    :param resource: The name of the resource file to read.
    :return: The full contents of the resource as bytes.
    :rtype: bytes
    """
    return importlib.resources.files(package).joinpath(resource).read_bytes()
