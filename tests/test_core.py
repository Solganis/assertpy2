from assertpy2 import assert_that


def test_fmt_items_empty():
    ab = assert_that(None)
    assert_that(ab._fmt_items([])).is_equal_to("<>")


def test_fmt_items_single():
    ab = assert_that(None)
    assert_that(ab._fmt_items([1])).is_equal_to("<1>")
    assert_that(ab._fmt_items(["foo"])).is_equal_to("<foo>")
    assert_that(ab._fmt_items([("bar", "baz")])).is_equal_to("<('bar', 'baz')>")


def test_fmt_items_multiple():
    ab = assert_that(None)
    assert_that(ab._fmt_items([1, 2, 3])).is_equal_to("<1, 2, 3>")
    assert_that(ab._fmt_items(["a", "b", "c"])).is_equal_to("<'a', 'b', 'c'>")


def test_fmt_args_kwargs_empty():
    ab = assert_that(None)
    assert_that(ab._fmt_args_kwargs()).is_equal_to("")


def test_fmt_args_kwargs_single_arg():
    ab = assert_that(None)
    assert_that(ab._fmt_args_kwargs(1)).is_equal_to("1")
    assert_that(ab._fmt_args_kwargs("foo")).is_equal_to("'foo'")


def test_fmt_args_kwargs_multiple_args():
    ab = assert_that(None)
    assert_that(ab._fmt_args_kwargs(1, 2, 3)).is_equal_to("1, 2, 3")
    assert_that(ab._fmt_args_kwargs("a", "b", "c")).is_equal_to("'a', 'b', 'c'")


def test_fmt_args_kwargs_single_kwarg():
    ab = assert_that(None)
    assert_that(ab._fmt_args_kwargs(a=1)).is_equal_to("'a': 1")
    assert_that(ab._fmt_args_kwargs(f="foo")).is_equal_to("'f': 'foo'")


def test_fmt_args_kwargs_multiple_kwargs():
    ab = assert_that(None)
    assert_that(ab._fmt_args_kwargs(a=1, b=2, c=3)).is_equal_to("'a': 1, 'b': 2, 'c': 3")
    assert_that(ab._fmt_args_kwargs(a="a", b="b", c="c")).is_equal_to("'a': 'a', 'b': 'b', 'c': 'c'")


def test_fmt_args_kwargs_multiple_both():
    ab = assert_that(None)
    assert_that(ab._fmt_args_kwargs(1, 2, 3, a=4, b=5, c=6)).is_equal_to("1, 2, 3, 'a': 4, 'b': 5, 'c': 6")
    assert_that(ab._fmt_args_kwargs("a", "b", "c", d="g", e="h", f="i")).is_equal_to(
        "'a', 'b', 'c', 'd': 'g', 'e': 'h', 'f': 'i'"
    )


def test_check_dict_like_empty_dict():
    ab = assert_that(None)
    assert_that(ab._check_dict_like({}))


def test_check_dict_like_not_iterable():
    ab = assert_that(None)
    assert_that(ab._check_dict_like).raises(TypeError).when_called_with(123).is_equal_to(
        "val <int> is not dict-like: not iterable"
    )


def test_check_dict_like_missing_keys():
    ab = assert_that(None)
    assert_that(ab._check_dict_like).raises(TypeError).when_called_with("foo").is_equal_to(
        "val <str> is not dict-like: missing keys()"
    )


def test_check_dict_like_bool():
    ab = assert_that(None)
    assert_that(ab._check_dict_like({}, return_as_bool=True)).is_true()
    assert_that(ab._check_dict_like(123, return_as_bool=True)).is_false()
    assert_that(ab._check_dict_like("foo", return_as_bool=True)).is_false()
