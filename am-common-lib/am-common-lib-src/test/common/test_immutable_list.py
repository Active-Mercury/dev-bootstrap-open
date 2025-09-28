from typing import Any

from assertpy import assert_that
from assertpy import soft_assertions
import pytest

from am_common_lib.common import ImmutableList


@pytest.fixture(scope="module")
def sample_list() -> list[Any]:
    return ["Item", 1, True]


@pytest.fixture(scope="module")
def imm(sample_list: list[Any]) -> ImmutableList[Any]:
    return ImmutableList(sample_list)


def test_is_list(imm: ImmutableList[Any]) -> None:
    assert_that(imm).is_instance_of(list)


def test_get(imm: ImmutableList[Any]) -> None:
    with soft_assertions():
        assert_that(imm[0]).described_as("get 0").is_equal_to("Item")
        assert_that(imm[1]).described_as("get 1").is_equal_to(1)
        assert_that(imm[2]).described_as("get 2").is_true()


def test_len_and_contains_and_iter(
    sample_list: list[Any], imm: ImmutableList[Any]
) -> None:
    with soft_assertions():
        # length
        assert_that(len(imm)).is_equal_to(len(sample_list))
        # membership
        assert_that("Item" in imm).is_true()
        assert_that(False in imm).is_false()
        # iteration
        assert_that(list(iter(imm))).is_equal_to(sample_list)


def test_index_and_count(sample_list: list[Any], imm: ImmutableList[Any]) -> None:
    # index()
    assert_that(imm.index("Item")).is_equal_to(sample_list.index("Item"))
    # count()
    assert_that(imm.count(True)).is_equal_to(sample_list.count(True))


def test_slice_returns_immutable_list(imm: ImmutableList[Any]) -> None:
    sliced = imm[0:2]
    # slicing should yield a new ImmutableList of the same contents
    assert_that(isinstance(sliced, ImmutableList)).is_true()
    assert_that(list(sliced)).is_equal_to(["Item", 1])


def test_equality_and_inequality(
    sample_list: list[Any], imm: ImmutableList[Any]
) -> None:
    # compare to underlying list
    assert_that(imm == sample_list).is_true()
    # compare to another ImmutableList with same contents
    assert_that(imm == ImmutableList(sample_list)).is_true()
    # different contents → not equal
    assert_that(imm != ImmutableList(sample_list + ["X"])).is_true()


def test_str(imm: ImmutableList[Any], sample_list: list[Any]) -> None:
    assert_that(str(imm)).is_equal_to(str(sample_list))


def test_repr(imm: ImmutableList[Any], sample_list: list[Any]) -> None:
    """Asserts that the value returned by repr() can be used to reconstruct the
    immutable list.

    Requires the class to be imported by name.
    """
    recreated = eval(repr(imm))
    assert_that(recreated).is_instance_of(ImmutableList)
    assert_that(recreated).is_equal_to(sample_list)
    assert_that(recreated).is_equal_to(imm)


@pytest.mark.parametrize(
    "expr",
    [
        # list methods
        "imm.append('New')",
        "imm.extend([2, 3])",
        "imm.insert(0, 'New')",
        "imm.remove('Item')",
        "imm.pop()",
        "imm.clear()",
        "imm.sort()",
        "imm.reverse()",
    ],
)
def test_eval_write_operations_raise(imm: ImmutableList[Any], expr: str) -> None:
    # evaluate each mutation op inside a TypeError context
    with pytest.raises(TypeError):
        eval(expr)


@pytest.mark.parametrize(
    "stmt",
    [
        # item assignment
        "imm[0] = 'New'",
        # slice assignment
        "imm[1:2] = [2]",
        # delete item
        "del imm[0]",
        # delete slice
        "del imm[1:2]",
        # in-place operators
        "imm += [4]",
        "imm *= 2",
    ],
)
def test_exec_write_operations_raise(imm: ImmutableList[Any], stmt: str) -> None:
    # execute each mutation statement inside a TypeError context
    with pytest.raises(TypeError):
        exec(stmt)


def test_sorting_fails() -> None:
    arr: list[int] = [2, 1, 5]
    imm: ImmutableList[int] = ImmutableList(arr)
    assert_that(imm).is_equal_to(arr)
    with pytest.raises(TypeError):
        imm.sort()
    assert_that(imm).is_equal_to(arr)


def test_slice() -> None:
    arr: ImmutableList[Any] = ImmutableList([1, "Hello", None, False])
    slc = arr[0:2]
    assert_that(slc).is_equal_to([1, "Hello"])
    assert_that(slc).is_instance_of(ImmutableList)
    assert_that(arr).is_equal_to([1, "Hello", None, False])

    with pytest.raises(TypeError):
        slc[1] = "Noooo"
    assert_that(slc).is_equal_to([1, "Hello"])
    assert_that(arr).is_equal_to([1, "Hello", None, False])
