import json
from typing import Union

from .immutable_dict import ImmutableDict
from .immutable_list import ImmutableList


# Type definitions for JSON structures
JSONPrimitive = Union[str, int, float, bool, None]
JSONValue = Union[JSONPrimitive, "JSONDict", "JSONList"]
JSONDict = dict[str, JSONValue]
JSONList = list[JSONValue]

# Type definitions for immutable JSON structures
ImmutableJSONDict = ImmutableDict[str, "ImmutableJSONValue"]
ImmutableJSONList = ImmutableList["ImmutableJSONValue"]
ImmutableJSONValue = Union[JSONPrimitive, ImmutableJSONDict, ImmutableJSONList]


def parse_json_immutable(json_str: str) -> ImmutableJSONValue:
    """Parse a JSON string and return an immutable result.

    Arrays are converted to ImmutableList and objects are converted to ImmutableDict.
    The conversion is recursive, so nested structures are also made immutable.

    Args:
        json_str: JSON string to parse

    Returns:
        Immutable version of the parsed JSON data
    """

    def _make_immutable(obj: JSONValue) -> ImmutableJSONValue:
        if isinstance(obj, dict):
            return ImmutableDict({k: _make_immutable(v) for k, v in obj.items()})
        elif isinstance(obj, list):
            return ImmutableList([_make_immutable(item) for item in obj])
        else:
            return obj

    parsed = json.loads(json_str)
    return _make_immutable(parsed)
