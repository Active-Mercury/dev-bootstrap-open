from assertpy import assert_that

from am_common_lib.docker_util.util import get_container_name_base
from am_common_lib.docker_util.util import to_base_54


def test_get_container_name_basic() -> None:
    assert_that(get_container_name_base("python-dev")).is_equal_to("python-dev")


def test_get_container_name_disallowed_chars() -> None:
    assert_that(get_container_name_base("mysql:5.7")).is_equal_to("mysql_5.7")
    assert_that(get_container_name_base("archivebox/archivebox:latest")).is_equal_to(
        "archivebox_archivebox_latest"
    )
    assert_that(get_container_name_base("my image@2")).is_equal_to("my_image_2")


def test_get_container_name_allowed_chars_preserved() -> None:
    name = "foo-bar.baz_123"
    assert_that(get_container_name_base(name)).is_equal_to(name)


def test_get_container_name_spcl_chars_truncate() -> None:
    img = ".name$with%spcl!chars"
    # Should start with alphanumeric and be truncated to exactly length 10
    result = get_container_name_base(img, max_length=10)
    assert_that(len(result)).is_equal_to(10)
    # Regex: first char alnum, rest allowed chars
    assert_that(result).matches(r"^[A-Za-z0-9][A-Za-z0-9_.-]{9}$")
    assert_that(result[1:]).is_equal_to("pcl_chars")


def test_get_container_name_max_length_too_small_raises() -> None:
    # max_length < 2 in invalid-start branch should raise
    assert_that(lambda: get_container_name_base("$$$", max_length=1)).raises(ValueError)


def test_to_base_54() -> None:
    assert_that(to_base_54(b"")).is_equal_to("")
    assert_that(to_base_54(b"\x00")).is_equal_to("2")
    inp = bytes(
        [119, 126, 125, 254, 23, 144, 58, 210, 3, 213, 212, 168, 27, 97, 108, 210]
    )
    assert_that(to_base_54(inp)).is_equal_to("3EBJn55PNpUTnjjJAGRKar2")
