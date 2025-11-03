import json
from typing import Any

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from am_common_lib.common import ImmutableDict
from am_common_lib.common import ImmutableList
from am_common_lib.common import parse_json_immutable


def _is_deeply_immutable(obj: Any) -> bool:
    if isinstance(obj, (str, int, float, bool, type(None))):
        return True
    if isinstance(obj, ImmutableDict):
        return all(_is_deeply_immutable(v) for v in obj.values()) and all(
            isinstance(k, str) for k in obj
        )
    if isinstance(obj, ImmutableList):
        return all(_is_deeply_immutable(v) for v in obj)
    return False


@pytest.mark.parametrize(
    "json_str,case_name",
    [
        # Primitive values (not wrapped in objects/arrays)
        ('"string"', "primitive_string"),
        ("42", "primitive_integer"),
        ("3.14", "primitive_float"),
        ("true", "primitive_boolean_true"),
        ("false", "primitive_boolean_false"),
        ("null", "primitive_null"),
        # Empty structures
        ("{}", "empty_object"),
        ("[]", "empty_array"),
        ('{"key": "value"}', "simple_object"),
        ('["item1", "item2"]', "simple_array"),
        ('{"nested": {"inner": "value"}}', "nested_object"),
        ('[{"item": "value"}, {"item2": "value2"}]', "array_of_objects"),
        ('{"mixed": [1, 2, {"nested": true}]}', "mixed_nested_structure"),
        (
            '{"deep": {"level2": {"level3": {"level4": "deep_value"}}}}',
            "deeply_nested_object",
        ),
        ("[1, 2, [3, 4, [5, 6]]]", "nested_arrays"),
        (
            (
                '{"primitives": {'
                '"string": "text", "number": 42, "float": 3.14, '
                '"boolean": true, "null": null}}'
            ),
            "all_primitive_types",
        ),
        ('{"unicode": "café", "emoji": "🚀", "chinese": "中文"}', "unicode_strings"),
        (
            (
                '{"special_chars": "line1\\nline2\\ttabbed", '
                '"quotes": "he said \\"hello\\""}'
            ),
            "special_characters",
        ),
        ('{"large_array": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}', "large_array"),
        ('{"boolean_array": [true, false, true]}', "boolean_array"),
        ('{"number_array": [1, -1, 0, 3.14, -2.5]}', "number_array"),
        ('{"string_array": ["a", "b", "c", "d"]}', "string_array"),
        (
            '{"mixed_array": [1, "string", true, null, {"nested": "value"}]}',
            "mixed_type_array",
        ),
        (
            '{"empty_nested": {"empty_dict": {}, "empty_list": []}}',
            "empty_nested_structures",
        ),
        ('{"duplicate_keys": {"a": 1, "a": 2}}', "duplicate_keys"),
        ('{"sparse_array": [1, null, 3, null, 5]}', "sparse_array_with_nulls"),
        (
            (
                '{"complex": {'
                '"users": [{"name": "Alice", "age": 30}, '
                '{"name": "Bob", "age": 25}], '
                '"metadata": {"count": 2}}}'
            ),
            "complex_real_world_structure",
        ),
    ],
)
def test_parse_json_immutable_various_cases(json_str: str, case_name: str) -> None:
    """Test parse_json_immutable with various JSON structures.

    Verifies that:
    1. The result equals the standard json.loads result
    2. The result is deeply immutable
    """
    # Parse with standard JSON
    expected = json.loads(json_str)

    # Parse with immutable version
    result = parse_json_immutable(json_str)

    with soft_assertions():
        # Results should be equal
        assert_that(result).described_as(
            f"Result for {case_name} should equal json.loads result"
        ).is_equal_to(expected)

        # Result should be deeply immutable
        assert_that(_is_deeply_immutable(result)).described_as(
            f"Result for {case_name} should be deeply immutable"
        ).is_true()
