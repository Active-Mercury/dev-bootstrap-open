import json
from typing import Any

from assertpy import assert_that
from assertpy import soft_assertions
import pytest
from util import get_not_overridden_attributes

from am_common_lib.common import ImmutableDict


def test_non_overriden_attributes() -> None:
    not_overridden = get_not_overridden_attributes(ImmutableDict, dict)

    # These are the safe attributes that are expected to remain not overridden
    expected_safe_attributes = {
        # Read-only dictionary operations
        "__getitem__",
        "__init__",
        "get",
        "keys",
        "values",
        "items",
        "copy",
        "__len__",
        "__iter__",
        "__contains__",
        "__reversed__",
        # Comparison and equality operations
        "__eq__",
        "__ne__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
        "__or__",
        "__ror__",
        # Standard object methods
        "__new__",
        "__class__",
        "__dir__",
        "__format__",
        "__getattribute__",
        "__reduce__",
        "__reduce_ex__",
        "__getstate__",
        "__sizeof__",
    }

    assert_that(not_overridden).is_equal_to(expected_safe_attributes)


def test_builtin_dict_has_no_new_members() -> None:
    expected_members = {
        "__class__",
        "__class_getitem__",
        "__contains__",
        "__delattr__",
        "__delitem__",
        "__dir__",
        "__doc__",
        "__eq__",
        "__format__",
        "__ge__",
        "__getattribute__",
        "__getitem__",
        "__getstate__",
        "__gt__",
        "__hash__",
        "__init__",
        "__init_subclass__",
        "__ior__",
        "__iter__",
        "__le__",
        "__len__",
        "__lt__",
        "__ne__",
        "__new__",
        "__or__",
        "__reduce__",
        "__reduce_ex__",
        "__repr__",
        "__reversed__",
        "__ror__",
        "__setattr__",
        "__setitem__",
        "__sizeof__",
        "__str__",
        "__subclasshook__",
        "clear",
        "copy",
        "fromkeys",
        "get",
        "items",
        "keys",
        "pop",
        "popitem",
        "setdefault",
        "update",
        "values",
    }

    assert_that(set(dir(dict))).is_equal_to(expected_members)


@pytest.fixture(scope="module")
def sample_mapping() -> dict[str, int]:
    return {"a": 1, "b": 2}


@pytest.fixture(scope="module")
def imm(sample_mapping: dict[str, int]) -> ImmutableDict[str, int]:
    return ImmutableDict(sample_mapping)


def test_getitem_existing_key_returns_value(imm: ImmutableDict[str, int]) -> None:
    with soft_assertions():
        assert_that(imm["a"]).described_as("__getitem__ for 'a'").is_equal_to(1)
        assert_that(imm["b"]).described_as("__getitem__ for 'b'").is_equal_to(2)


def test_getitem_nonexistent_key_raises_key_error(imm: ImmutableDict[str, int]) -> None:
    with pytest.raises(KeyError):
        _ = imm["z"]


def test_str(imm: ImmutableDict[str, int], sample_mapping: dict[str, int]) -> None:
    assert_that(str(imm)).is_equal_to(str(sample_mapping))


def test_repr(imm: ImmutableDict[str, int], sample_mapping: dict[str, int]) -> None:
    assert_that(eval(repr(imm))).is_equal_to(imm)


def test_get_method_with_and_without_default(imm: ImmutableDict[str, int]) -> None:
    with soft_assertions():
        assert_that(imm.get("a")).is_equal_to(1)
        assert_that(imm.get("z")).is_none()
        assert_that(imm.get("z", 42)).is_equal_to(42)


def test_len_iter_contains(
    imm: ImmutableDict[str, int], sample_mapping: dict[str, int]
) -> None:
    assert_that(len(imm)).is_equal_to(len(sample_mapping))
    # iteration order may matter if implementation preserves insertion order
    assert_that(list(iter(imm))).is_equal_to(list(sample_mapping.keys()))
    assert_that("a" in imm).is_true()
    assert_that("z" in imm).is_false()


def test_keys_items_values(
    imm: ImmutableDict[str, int], sample_mapping: dict[str, int]
) -> None:
    # compare as sets in case order isn’t important
    assert_that(set(imm.keys())).is_equal_to(set(sample_mapping.keys()))
    assert_that(set(imm.values())).is_equal_to(set(sample_mapping.values()))
    assert_that(set(imm.items())).is_equal_to(set(sample_mapping.items()))


def test_copy_and_dict_cast(
    imm: ImmutableDict[str, int], sample_mapping: dict[str, int]
) -> None:
    # .copy()
    copy = imm.copy()
    assert_that(copy).is_equal_to(sample_mapping)
    # casting to dict
    normal = dict(imm)
    assert_that(normal).is_instance_of(dict).is_equal_to(sample_mapping)
    # ensure modifying the normal copy does not touch the original
    normal["c"] = 3
    assert_that("c" in imm).is_false()


def test_union_operator_and_unpacking_do_not_mutate(
    imm: ImmutableDict[str, int],
) -> None:
    # Python 3.9+ | operator
    unioned = {"c": 3} | imm
    assert_that(unioned).is_instance_of(dict)
    assert_that(unioned).contains_entry({"c": 3})
    assert_that(imm).does_not_contain_key("c")
    # unpacking
    unpacked = {**imm, "d": 4}
    assert_that(unpacked).contains_entry({"d": 4})
    assert_that(imm).does_not_contain_key("d")


def test_equality_and_hashability(
    imm: ImmutableDict[str, int], sample_mapping: dict[str, int]
) -> None:
    other_same: ImmutableDict[str, int] = ImmutableDict({"b": 2, "a": 1})
    assert_that(imm).is_equal_to(other_same)
    assert_that(imm).is_equal_to(sample_mapping)
    # hashability: can live in a set
    s = {imm, other_same}
    assert_that(len(s)).is_equal_to(1)
    assert_that(imm in s).is_true()


def test_json_serialization(
    imm: ImmutableDict[str, int], sample_mapping: dict[str, int]
) -> None:
    assert_that(_to_json(imm)).is_equal_to(_to_json(sample_mapping))
    dumped = json.dumps(imm, sort_keys=True)
    expected = json.dumps(sample_mapping, sort_keys=True)
    assert_that(dumped).is_equal_to(expected)


@pytest.mark.parametrize(
    "method,args",
    [
        ("__setitem__", ("c", 3)),
        ("__delitem__", ("a",)),
        ("pop", ("a",)),
        ("popitem", ()),
        ("clear", ()),
        ("update", ({"c": 3},)),
        ("setdefault", ("c", 3)),
        ("__ior__", ({"c": 3},)),
    ],
)
def test_mutating_methods_raise_type_error(
    imm: ImmutableDict[str, int], method: str, args: tuple[Any, ...]
) -> None:
    bak = imm.copy()
    fn = getattr(imm, method)
    with pytest.raises(TypeError):
        fn(*args)

    with soft_assertions():
        assert_that(imm).described_as("equality").is_equal_to(bak)
        assert_that(tuple(imm.keys())).described_as("iteration order").is_equal_to(
            tuple(bak.keys())
        )


def test_assignment_and_deletion_syntax_raise(imm: ImmutableDict[str, int]) -> None:
    bak = imm.copy()
    with pytest.raises(TypeError):
        imm["c"] = 3
    with pytest.raises(TypeError):
        del imm["a"]

    with soft_assertions():
        assert_that(imm).described_as("equality").is_equal_to(bak)
        assert_that(tuple(imm.keys())).described_as("iteration order").is_equal_to(
            tuple(bak.keys())
        )


def test_ior_operator_raises_type_error(imm: ImmutableDict[str, int]) -> None:
    """Test that the |= operator raises TypeError."""
    bak = imm.copy()
    with pytest.raises(TypeError):
        imm |= {"c": 3}

    with soft_assertions():
        assert_that(imm).described_as("equality").is_equal_to(bak)
        assert_that(tuple(imm.keys())).described_as("iteration order").is_equal_to(
            tuple(bak.keys())
        )


def test_attribute_modification_raises_type_error(imm: ImmutableDict[str, int]) -> None:
    """Test that attribute assignment and deletion raise TypeError."""
    with pytest.raises(TypeError):
        imm.some_attribute = "value"

    with pytest.raises(TypeError):
        delattr(imm, "some_attribute")


# ------------------------------------- OLD


@pytest.mark.skip
def test_read_operations() -> None:
    x = {"a": 1, "b": 2}
    imm: ImmutableDict[str, int] = ImmutableDict(x)

    # __getitem__ / KeyError on missing
    assert_that(imm["a"]).is_equal_to(1)
    assert_that(lambda: imm["c"]).raises(KeyError)

    # get with and without default
    assert_that(imm.get("b")).is_equal_to(2)
    assert_that(imm.get("c")).is_none()
    assert_that(imm.get("c", "def")).is_equal_to("def")

    # views: keys, values, items
    assert_that(list(imm.keys())).is_equal_to(list(x.keys()))
    assert_that(list(imm.values())).is_equal_to(list(x.values()))
    assert_that(list(imm.items())).is_equal_to(list(x.items()))

    # iteration and length
    assert_that(list(iter(imm))).is_equal_to(list(x))
    assert_that(len(imm)).is_equal_to(len(x))

    # membership
    assert_that("a" in imm).is_true()
    assert_that("c" in imm).is_false()

    # repr/str
    assert_that(repr(imm)).is_equal_to(repr(x))
    assert_that(str(imm)).is_equal_to(str(x))

    # JSON
    assert_that(_to_json(imm)).described_as("JSON equality").is_equal_to(_to_json(x))

    # equality + hashability + set-behavior
    imm2: ImmutableDict[str, int] = ImmutableDict({"b": 2, "a": 1})
    assert_that(imm2 == imm).is_true()
    assert_that(hash(imm2)).is_equal_to(hash(imm))
    # putting both into a set yields only one element
    s = {imm, imm2}
    assert_that(s).is_length(1)
    assert_that(s).contains(imm)


@pytest.mark.parametrize(
    "name, operation",
    [
        ("__setitem__", lambda d: d.__setitem__("c", 3)),
        ("__delitem__", lambda d: d.__delitem__("a")),
        ("clear", lambda d: d.clear()),
        ("pop", lambda d: d.pop("a")),
        ("popitem", lambda d: d.popitem()),
        ("update", lambda d: d.update({"c": 3})),
        ("setdefault", lambda d: d.setdefault("c", 3)),
        ("__ior__", lambda d: d.__ior__({"c": 3})),
    ],
)
def test_mutation_operations_raise(name: str, operation: Any) -> None:
    x = {"a": 1, "b": 2}
    imm: ImmutableDict[str, int] = ImmutableDict(x)
    # every mutating op must raise TypeError
    assert_that(lambda: operation(imm)).described_as(
        f"Operation {name} should not be allowed"
    ).raises(TypeError)


def test_iteration_order() -> None:
    imm1: ImmutableDict[str, int] = ImmutableDict({"a": 1, "b": 2})
    imm2: ImmutableDict[str, int] = ImmutableDict({"b": 2, "a": 1})
    assert_that(imm2).described_as("equality").is_equal_to(imm1)
    assert_that(hash(imm2)).described_as("hash() equality").is_equal_to(hash(imm1))
    assert_that(imm1 == imm2).described_as("== equality").is_true()
    assert_that(str(imm2)).described_as("str() inequality").is_not_equal_to(str(imm1))


def _to_json(obj: Any, *, run_tests: bool = True) -> str:
    ret = json.dumps(obj, separators=(",", ":"), ensure_ascii=True)
    if run_tests:
        reloaded_obj = json.loads(ret)
        assert_that(reloaded_obj).is_equal_to(obj)
        assert_that(_to_json(reloaded_obj, run_tests=False)).described_as(
            "JSON roundtripping"
        ).is_equal_to(ret)
    return ret
