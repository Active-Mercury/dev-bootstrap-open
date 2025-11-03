"""Utilities for working with JSON and immutable JSON values."""

from __future__ import annotations

import json

from .immutable_dict import ImmutableDict
from .immutable_list import ImmutableList


# Type definitions for JSON structures
type JSONPrimitive = str | int | float | bool | None
type JSONValue = JSONPrimitive | "JSONDict" | "JSONList"
type JSONDict = dict[str, "JSONValue"]
type JSONList = list["JSONValue"]

# Type definitions for immutable JSON structures
type ImmutableJSONDict = ImmutableDict[str, "ImmutableJSONValue"]
type ImmutableJSONList = ImmutableList["ImmutableJSONValue"]
type ImmutableJSONValue = JSONPrimitive | "ImmutableJSONDict" | "ImmutableJSONList"


def parse_json_immutable(json_str: str) -> ImmutableJSONValue:
    """Parse a JSON string and return an immutable result.

    Arrays are converted to :class:`ImmutableList` and objects are converted to
    :class:`ImmutableDict`. The conversion is recursive, so nested structures
    are also made immutable.

    :param str json_str: JSON string to parse.
    :return: Immutable version of the parsed JSON data.
    :rtype: ImmutableJSONValue
    """

    def _make_immutable(obj: JSONValue) -> ImmutableJSONValue:
        if isinstance(obj, dict):
            return ImmutableDict({k: _make_immutable(v) for k, v in obj.items()})
        if isinstance(obj, list):
            return ImmutableList([_make_immutable(item) for item in obj])
        return obj

    parsed = json.loads(json_str)
    return _make_immutable(parsed)
