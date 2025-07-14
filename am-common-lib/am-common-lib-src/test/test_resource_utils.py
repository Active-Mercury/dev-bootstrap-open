from assertpy import assert_that
import pytest

from am_common_lib.resource_utils import open_resource_binary
from am_common_lib.resource_utils import open_resource_text
from am_common_lib.resource_utils import read_resource_bytes
from am_common_lib.resource_utils import read_resource_text


@pytest.mark.parametrize(
    "fn, pkg, res",
    [
        (open_resource_text, "am_common_lib", "no_such_file.txt"),
        (open_resource_binary, "am_common_lib", "no_such_file.bin"),
        (read_resource_text, "am_common_lib", "no_such_file.txt"),
        (read_resource_bytes, "am_common_lib", "no_such_file.bin"),
    ],
)
def test_resource_not_found(fn, pkg, res) -> None:
    with pytest.raises(FileNotFoundError):
        fn(pkg, res)


def test_read_resource_text() -> None:
    assert_that(read_resource_text("resources.txt", "resource_exemplar")).is_equal_to(
        "I am a resource file for am-common-lib."
    )


def test_read_resource_bytes() -> None:
    assert_that(read_resource_bytes("resources.txt", "resource_exemplar")).is_equal_to(
        b"I am a resource file for am-common-lib."
    )


def test_open_resource_binary() -> None:
    expected = b"I am a resource file for am-common-lib."
    with open_resource_binary("resources.txt", "resource_exemplar") as f:
        b1 = f.read(5)
        assert_that(b1).is_equal_to(expected[:5])
        b2 = f.read()
        assert_that(b1 + b2).is_equal_to(expected)


def test_open_text() -> None:
    expected = "I am a resource file for am-common-lib."
    with open_resource_text("resources.txt", "resource_exemplar") as f:
        s1 = f.read(5)
        assert_that(s1).is_equal_to(expected[:5])
        s2 = f.read()
        assert_that(s1 + s2).is_equal_to(expected)
