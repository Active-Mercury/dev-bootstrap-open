"""Common utilities and data structures.

This module provides immutable data structures and JSON utilities.
"""

from .immutable_dict import ImmutableDict
from .immutable_list import ImmutableList
from .json_util import ImmutableJSONDict
from .json_util import ImmutableJSONList
from .json_util import ImmutableJSONValue
from .json_util import JSONDict
from .json_util import JSONList
from .json_util import JSONPrimitive
from .json_util import JSONValue
from .json_util import parse_json_immutable


__all__ = [
    # Immutable data structures
    "ImmutableDict",
    "ImmutableList",
    # JSON type definitions
    "JSONPrimitive",
    "JSONValue",
    "JSONDict",
    "JSONList",
    "ImmutableJSONValue",
    "ImmutableJSONDict",
    "ImmutableJSONList",
    # JSON utilities
    "parse_json_immutable",
]
