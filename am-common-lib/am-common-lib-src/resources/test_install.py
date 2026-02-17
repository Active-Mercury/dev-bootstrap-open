"""Packaging sanity tests for the ``am-common-lib`` distribution.

These tests verify that the built and installed package can be imported and
that key public APIs are accessible.  They use only the standard library
``unittest`` framework so they can run in a minimal virtual environment that
has nothing besides the package under test.
"""

import unittest


class TestPackageImports(unittest.TestCase):
    """Verify that all public subpackages import without errors."""

    def test_import_root_package(self):
        import am_common_lib

        self.assertTrue(hasattr(am_common_lib, "__name__"))

    def test_import_common_subpackage(self):
        from am_common_lib.common import ImmutableDict
        from am_common_lib.common import ImmutableList
        from am_common_lib.common import parse_json_immutable

        self.assertIsNotNone(ImmutableDict)
        self.assertIsNotNone(ImmutableList)
        self.assertIsNotNone(parse_json_immutable)

    def test_import_json_type_aliases(self):
        from am_common_lib.common import ImmutableJSONDict
        from am_common_lib.common import ImmutableJSONList
        from am_common_lib.common import ImmutableJSONValue
        from am_common_lib.common import JSONDict
        from am_common_lib.common import JSONList
        from am_common_lib.common import JSONPrimitive
        from am_common_lib.common import JSONValue

        for alias in (
            JSONPrimitive,
            JSONValue,
            JSONDict,
            JSONList,
            ImmutableJSONValue,
            ImmutableJSONDict,
            ImmutableJSONList,
        ):
            self.assertIsNotNone(alias)

    def test_import_docker_util(self):
        from am_common_lib.docker_util import ImageNames

        self.assertIsNotNone(ImageNames)

    def test_import_docker_runner(self):
        from am_common_lib.docker_util.docker_runner import DockerRunner

        self.assertTrue(callable(DockerRunner))

    def test_import_resource_utils(self):
        from am_common_lib import resource_utils

        for fn_name in (
            "read_resource_text",
            "read_resource_bytes",
            "open_resource_text",
            "open_resource_binary",
        ):
            self.assertTrue(
                callable(getattr(resource_utils, fn_name)),
                f"{fn_name} should be callable",
            )


class TestBasicFunctionality(unittest.TestCase):
    """Verify basic functionality of core types after installation."""

    def test_immutable_dict_creation_and_lookup(self):
        from am_common_lib.common import ImmutableDict

        d = ImmutableDict({"a": 1, "b": 2})
        self.assertEqual(d["a"], 1)
        self.assertEqual(len(d), 2)

    def test_immutable_dict_blocks_mutation(self):
        from am_common_lib.common import ImmutableDict

        d = ImmutableDict({"x": 10})
        with self.assertRaises(TypeError):
            d["y"] = 20  # type: ignore[index]

    def test_immutable_dict_is_hashable(self):
        from am_common_lib.common import ImmutableDict

        d = ImmutableDict({"a": 1})
        self.assertIsInstance(hash(d), int)

    def test_immutable_list_creation_and_lookup(self):
        from am_common_lib.common import ImmutableList

        lst = ImmutableList([10, 20, 30])
        self.assertEqual(lst[0], 10)
        self.assertEqual(len(lst), 3)

    def test_immutable_list_blocks_mutation(self):
        from am_common_lib.common import ImmutableList

        lst = ImmutableList([1, 2, 3])
        with self.assertRaises(TypeError):
            lst[0] = 99  # type: ignore[index]

    def test_parse_json_immutable_roundtrip(self):
        from am_common_lib.common import ImmutableDict
        from am_common_lib.common import ImmutableList
        from am_common_lib.common import parse_json_immutable

        result = parse_json_immutable('{"key": [1, 2, 3], "nested": {"a": true}}')
        self.assertIsInstance(result, ImmutableDict)
        self.assertIsInstance(result["key"], ImmutableList)
        self.assertEqual(result["key"][0], 1)
        self.assertIsInstance(result["nested"], ImmutableDict)
        self.assertIs(result["nested"]["a"], True)


class TestPackageMetadata(unittest.TestCase):
    """Verify package metadata is accessible."""

    def test_version_is_present(self):
        from importlib.metadata import version

        v = version("am-common-lib")
        self.assertTrue(len(v) > 0, "version string should not be empty")

    def test_version_starts_with_expected_prefix(self):
        from importlib.metadata import version

        v = version("am-common-lib")
        self.assertTrue(
            v.startswith("0."),
            f"Expected version to start with '0.', got '{v}'",
        )


if __name__ == "__main__":
    unittest.main()
