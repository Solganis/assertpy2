import collections

import pytest

from assertpy2 import assert_that


def test_ignore_key():
    assert_that({"a": 1}).is_equal_to({}, ignore="a")
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore="b")
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 2}, ignore="c")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1}, ignore="b")


def test_ignore_list_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2, "c": 3}, ignore=[])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, ignore=["c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore=["b", "c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({}, ignore=["a", "b", "c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2, "c": 3}, ignore=["d"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"b": 2}, ignore=["c", "d", "e", "a"])


def test_ignore_set_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore={"b", "c"})
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({}, ignore=frozenset({"a", "b", "c"}))
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2, "c": 3}, ignore=set())
    # a set may carry nested-path tuples, same as a list
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2}}, ignore={("b", "y")})


def test_ignore_bytes_key():
    assert_that({b"a": 1, b"b": 2}).is_equal_to({b"a": 1}, ignore=b"b")


def test_ignore_rejects_one_shot_iterable():
    with pytest.raises(TypeError, match="ignore must be a key"):
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore=(key for key in ("b",)))
    with pytest.raises(TypeError, match="ignore must be a key"):
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore={"a": 1}.keys())


def test_ignore_deep_key():
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1}, ignore="b")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1}, ignore=[("b",)])
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2}}, ignore=("b", "y"))
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2}}, ignore=[("b", "y")])
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to(
        {"a": 1, "b": {"x": 2}}, ignore=[("b", "y"), ("b", "x", "j")]
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to({}, ignore=["a", "b"])
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to({"a": 1}, ignore="b")
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"a": 1, "b": {"c": 2}}, ignore=("b", "d")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"a": 1, "b": {"c": 2, "d": {"e": 3}}}, ignore=("b", "d", "f")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 6}}}}, ignore=("b", "d", "f", "y")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}, ignore=("b", "d", "f", "y", "foo")
    )


def test_ordered():
    ordered = collections.OrderedDict([("a", 1), ("b", 2)])
    assert_that(ordered).is_equal_to({"a": 1, "b": 2})


def test_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 3})
    assert_that(str(exc_info.value)).is_equal_to("Expected <{.., 'b': 2}> to be equal to <{.., 'b': 3}>, but was not.")


def test_failure_single_entry():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2})
    assert_that(str(exc_info.value)).is_equal_to("Expected <{'a': 1}> to be equal to <{'a': 2}>, but was not.")


def test_failure_multi_entry():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 3, "c": 3})
    assert_that(str(exc_info.value)).is_equal_to("Expected <{.., 'b': 2}> to be equal to <{.., 'b': 3}>, but was not.")


def test_failure_multi_entry_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 3, "c": 4})
    assert_that(str(exc_info.value)).contains("'b': 2").contains("'b': 3").contains("'c': 3").contains(
        "'c': 4"
    ).ends_with("but was not.")


def test_failure_deep_dict():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2, "y": 4}})
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {.., 'y': 3}}> to be equal to <{.., 'b': {.., 'y': 4}}>, but was not."
    )


def test_failure_deep_dict_single_key():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2}})
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {.., 'y': 3}}> to be equal to <{.., 'b': {..}}>, but was not."
    )


def test_failure_very_deep_dict():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
            {"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 6}}}}
        )
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {.., 'd': {.., 'f': {.., 'y': 5}}}}> to be equal to "
        "<{.., 'b': {.., 'd': {.., 'f': {.., 'y': 6}}}}>, but was not."
    )


def test_failure_ignore():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 3}, ignore="c")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': 2}> to be equal to <{.., 'b': 3}> ignoring keys <c>, but was not."
    )


def test_failure_ignore_single_entry():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, ignore="c")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> ignoring keys <c>, but was not."
    )


def test_failure_ignore_multi_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, ignore=["x", "y", "z"])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> ignoring keys <'x', 'y', 'z'>, but was not."
    )


def test_failure_ignore_multi_deep_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, ignore=[("q", "r", "s"), ("x", "y", "z")])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> ignoring keys <'q.r.s', 'x.y.z'>, but was not."
    )


def test_failure_ignore_mixed_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, ignore=["b", ("c"), ("d", "e"), ("q", "r", "s"), ("x", "y", "z")])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> ignoring keys <'b', 'c', 'd.e', 'q.r.s', 'x.y.z'>, but was not."
    )


def test_failure_int_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({1: "a", 2: "b"}).is_equal_to({1: "a", 3: "b"})
    assert_that(str(exc_info.value)).is_equal_to("Expected <{.., 2: 'b'}> to be equal to <{.., 3: 'b'}>, but was not.")


def test_failure_deep_int_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({1: "a", 2: {3: "b", 4: "c"}}).is_equal_to({1: "a", 2: {3: "b", 5: "c"}}, ignore=(2, 3))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 2: {.., 4: 'c'}}> to be equal to <{.., 2: {.., 5: 'c'}}> ignoring keys <2.3>, but was not."
    )


def test_failure_tuple_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1, 2): "a", (3, 4): "b"}).is_equal_to({(1, 2): "a", (3, 4): "c"})
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., (3, 4): 'b'}> to be equal to <{.., (3, 4): 'c'}>, but was not."
    )


def test_failure_tuple_keys_ignore():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1, 2): "a", (3, 4): "b"}).is_equal_to({(1, 2): "a", (3, 4): "c"}, ignore=(1, 2))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., (3, 4): 'b'}> to be equal to <{.., (3, 4): 'c'}> ignoring keys <1.2>, but was not."
    )


def test_failure_deep_tuple_keys_ignore():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1, 2): "a", (3, 4): {(5, 6): "b", (7, 8): "c"}}).is_equal_to(
            {(1, 2): "a", (3, 4): {(5, 6): "b", (7, 8): "d"}}, ignore=((3, 4), (5, 6))
        )
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., (3, 4): {.., (7, 8): 'c'}}> to be equal to "
        "<{.., (3, 4): {.., (7, 8): 'd'}}> ignoring keys <(3, 4).(5, 6)>, but was not."
    )


def test_failure_single_item_tuple_keys_ignore():
    # due to unpacking-fu, single item tuple keys must be tupled in ignore statement, so this works:
    assert_that({(1,): "a", (2,): "b"}).is_equal_to({(1,): "a", (2,): "c"}, ignore=((2,),))

    # but this fails:
    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1,): "a", (2,): "b"}).is_equal_to({(1,): "a"}, ignore=(2,))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., (2,): 'b'}> to be equal to <{..}> ignoring keys <2>, but was not."
    )


def test_failure_single_item_tuple_keys_ignore_error_msg():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1,): "a"}).is_equal_to({(1,): "b"}, ignore=((2,),))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{(1,): 'a'}> to be equal to <{(1,): 'b'}> ignoring keys <2>, but was not."
    )


def test_include_key():
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, include="a")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1}, include="a")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2, "y": 3}}, include="b")


def test_include_list_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2, "c": 3}, include=["a", "b", "c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, include=["a", "b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, include=["a"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"b": 2}, include=["b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"c": 3}, include=["c"])


def test_include_set_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, include={"a", "b"})
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, include=frozenset({"a"}))


def test_include_rejects_one_shot_iterable():
    with pytest.raises(TypeError, match="include must be a key"):
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, include=(key for key in ("a",)))


def test_include_deep_key():
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2, "y": 3}}, include="b")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2}}, include=("b", "x"))
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}, include="b"
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"c": 2}}, include=("b", "c")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"d": {"e": 3, "f": {"x": 4, "y": 5}}}}, include=("b", "d")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {
            "b": {
                "d": {
                    "e": 3,
                }
            }
        },
        include=("b", "d", "e"),
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"d": {"f": {"x": 4, "y": 5}}}}, include=("b", "d", "f")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"d": {"f": {"x": 4}}}}, include=("b", "d", "f", "x")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"d": {"f": {"y": 5}}}}, include=("b", "d", "f", "y")
    )


def test_failure_include():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, include="a")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> including keys <a>, but was not."
    )


def test_failure_include_missing():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 1}, include="b")
    assert_that(str(exc_info.value)).is_equal_to("Expected <{'a': 1}> to include key <b>, but did not include key <b>.")


def test_failure_include_multiple_missing():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 1}, include=["b", "c"])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to include keys <'b', 'c'>, but did not include keys <'b', 'c'>."
    )


def test_failure_include_deep_missing():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": {"b": 2}}).is_equal_to({"a": {"c": 3}}, include=("a", "c"))
    assert_that(str(exc_info.value)).is_equal_to("Expected <{'b': 2}> to include key <c>, but did not include key <c>.")


def test_failure_include_multi_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 3}, include=["a", "b"])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': 2}> to be equal to <{.., 'b': 3}> including keys <'a', 'b'>, but was not."
    )


def test_failure_include_deep_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": {"b": 1}}).is_equal_to({"a": {"b": 2}}, include=("a", "b"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': {'b': 1}}> to be equal to <{'a': {'b': 2}}> including keys <a.b>, but was not."
    )


def test_ignore_and_include_key():
    assert_that({"a": 1}).is_equal_to({}, ignore="a", include="a")
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore="b", include="a")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"y": 3}}, ignore=("b", "x"), include="b")


def test_ignore_and_include_list_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "c": 3}, ignore=["b"], include=["a", "b", "c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, ignore=["c"], include=["a", "b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore=["b", "c"], include=["a", "b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore=["c"], include=["a"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"b": 2}, ignore=["a"], include=["b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"c": 3}, ignore=["b"], include=["c"])


def test_ignore_and_include_deep_key():
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2, "y": 3}}, ignore="a", include="b")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2}}, ignore=("b", "y"), include=("b", "x"))
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"c": 2, "d": {"e": 3}}}, ignore=("b", "d", "f"), include="b"
    )


def test_ignore_deep_sibling_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    expected = {"a": 1, "b": {"c": 3, "d": {"e": 3}}}
    assert_that(actual).is_equal_to(expected, ignore=("b", "c"))


def test_ignore_nested_deep_sibling_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    expected = {"a": 1, "b": {"c": 2, "d": {"e": 4}}}
    assert_that(actual).is_equal_to(expected, ignore=("b", "d"))


def test_failure_deep_mismatch_when_ignoring_nested_deep_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    expected = {"a": 1, "b": {"c": 3, "d": {"e": 4}}}
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected, ignore=("b", "d"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {'c': 2, 'd': {'e': 3}}}> to be equal to "
        "<{.., 'b': {'c': 3, 'd': {'e': 4}}}> ignoring keys <b.d>, but was not."
    )


def test_failure_top_mismatch_when_ignoring_single_nested_key():
    actual = {"a": 1, "b": {"c": 2}}
    expected = {"a": 2, "b": {"c": 3}}
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected, ignore=("b", "c"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1, 'b': {'c': 2}}> to be equal to <{'a': 2, 'b': {'c': 3}}> ignoring keys <b.c>, but was not."
    )


def test_failure_top_mismatch_when_ignoring_single_nested_sibling_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    expected = {"a": 2, "b": {"c": 2, "d": {"e": 4}}}
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected, ignore=("b", "d"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1, 'b': {.., 'd': {'e': 3}}}> to be equal to "
        "<{'a': 2, 'b': {.., 'd': {'e': 4}}}> ignoring keys <b.d>, but was not."
    )


def test_failure_deep_mismatch_when_ignoring_double_nested_sibling_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}, "f": {"g": 5}}}
    expected = {"a": 1, "b": {"c": 2, "d": {"e": 4}, "f": {"g": 5}}}
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected, ignore=("b", "f", "g"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {.., 'd': {'e': 3}}}> to be equal to "
        "<{.., 'b': {.., 'd': {'e': 4}}}> ignoring keys <b.f.g>, but was not."
    )


def test_ignore_all_nested_keys():
    assert_that({"a": {"b": 1}}).is_equal_to({}, ignore="a")
    assert_that({"a": {"b": 1}}).is_equal_to({"a": {}}, ignore=[("a", "b")])
    assert_that({"a": {"b": 1, "c": 2}}).is_equal_to({"a": {}}, ignore=[("a", "b"), ("a", "c")])
    assert_that({"a": 1, "b": {"c": 2}}).is_equal_to({"b": {}}, ignore=["a", ("b", "c")])
