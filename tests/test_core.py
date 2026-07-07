import pytest

from assertpy2 import assert_that, assert_warn, soft_assertions


class TestValue:
    def test_value_returns_the_original_object(self):
        payload = {"a": 1}
        assert_that(assert_that(payload).value).is_same_as(payload)

    def test_value_after_passing_chain(self):
        assert_that(assert_that("foo").is_length(3).starts_with("f").value).is_equal_to("foo")

    def test_value_after_narrowing_assertions(self):
        order = {"status": "PAID"}
        assert_that(assert_that(order).is_not_none().is_instance_of(dict).value).is_same_as(order)

    def test_value_after_extracting_pivot(self):
        assert_that(assert_that([{"a": 1}, {"a": 2}]).extracting("a").value).is_equal_to([1, 2])

    def test_value_after_decoded_as_pivot(self):
        assert_that(assert_that(b"hi").decoded_as().value).is_equal_to("hi")

    def test_satisfies_with_typeis_predicate_runs_as_a_normal_predicate(self):
        # the TypeIs narrowing is purely static; at runtime satisfies() just runs the bool predicate
        class Order: ...

        class PaidOrder(Order): ...

        def is_paid(order):
            return isinstance(order, PaidOrder)

        paid = PaidOrder()
        assert_that(assert_that(paid).satisfies(is_paid).value).is_same_as(paid)
        with pytest.raises(AssertionError):
            assert_that(Order()).satisfies(is_paid)

    def test_value_passing_chain_in_soft_block_still_works(self):
        with soft_assertions():
            got = assert_that("foo").is_not_none().value
        assert_that(got).is_equal_to("foo")

    def test_value_after_failed_soft_assertion_raises_carrying_root_failure(self):
        # extract-and-continue is incoherent under collect-and-continue: refuse loudly, and surface
        # the underlying failure so its cause is not lost when the aggregated report is superseded
        with pytest.raises(TypeError) as exc, soft_assertions():
            _ = assert_that(None).is_not_none().value
        message = str(exc.value)
        assert_that(message).contains("cannot extract .value").contains("Expected not <None>, but was.")

    def test_taint_reason_is_the_root_failure_not_the_consequent(self):
        # is_not_none fails first (root: value is None); is_instance_of on None fails as a consequence.
        # first-wins means the surfaced message is the root, not the downstream instance-of failure.
        with pytest.raises(TypeError) as exc, soft_assertions():
            _ = assert_that(None).is_not_none().is_instance_of(str).value
        message = str(exc.value)
        assert_that(message).contains("Expected not <None>, but was.").does_not_contain("instance of class")

    def test_taint_covers_any_failed_assertion_not_only_narrowing(self):
        # intended general contract "extract only what was fully established": a failed non-narrowing
        # assertion (is_greater_than) taints .value exactly like a failed is_not_none would
        with pytest.raises(TypeError, match=r"cannot extract .value.*to be greater than"), soft_assertions():
            _ = assert_that(3).is_greater_than(10).value

    def test_value_after_failed_warn_assertion_raises(self):
        with pytest.raises(TypeError, match=r"cannot extract .value"):
            _ = assert_warn(None).is_not_none().value

    def test_taint_is_per_value_pivot_washes_orthogonal_failure(self):
        # the taint is per-value: a pivot begins a fresh builder. after a failed but ORTHOGONAL
        # assertion (is_length), extracting a real sub-value returns it cleanly; the block still
        # aggregate-raises the collected is_length failure at exit
        captured = []
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            captured.append(assert_that([{"a": 1}]).is_length(9).extracting("a").value)
        assert_that(captured).is_equal_to([[1]])

    def test_pivot_after_failed_is_not_none_raises_in_the_pivot_not_at_value(self):
        # adversarial: a pivot can never reach .value with a value derived from an unvalidated None.
        # extracting on the None left by a failed is_not_none raises in the pivot's own input check,
        # before .value - so per-value taint + pivot input-validation together close the poison path
        with pytest.raises(TypeError, match="val is not iterable"), soft_assertions():
            _ = assert_that(None).is_not_none().extracting("total").value

    def test_strict_value_is_never_tainted(self):
        # under strict a failed assertion raises before .value is reached, so the flag never trips
        assert_that(assert_that(5).is_greater_than(0).value).is_equal_to(5)


def test_fmt_items_empty():
    builder = assert_that(None)
    assert_that(builder._fmt_items([])).is_equal_to("<>")


def test_fmt_items_single():
    builder = assert_that(None)
    assert_that(builder._fmt_items([1])).is_equal_to("<1>")
    assert_that(builder._fmt_items(["foo"])).is_equal_to("<foo>")
    assert_that(builder._fmt_items([("bar", "baz")])).is_equal_to("<('bar', 'baz')>")


def test_fmt_items_multiple():
    builder = assert_that(None)
    assert_that(builder._fmt_items([1, 2, 3])).is_equal_to("<1, 2, 3>")
    assert_that(builder._fmt_items(["a", "b", "c"])).is_equal_to("<'a', 'b', 'c'>")


def test_fmt_args_kwargs_empty():
    builder = assert_that(None)
    assert_that(builder._fmt_args_kwargs()).is_equal_to("")


def test_fmt_args_kwargs_single_arg():
    builder = assert_that(None)
    assert_that(builder._fmt_args_kwargs(1)).is_equal_to("1")
    assert_that(builder._fmt_args_kwargs("foo")).is_equal_to("'foo'")


def test_fmt_args_kwargs_multiple_args():
    builder = assert_that(None)
    assert_that(builder._fmt_args_kwargs(1, 2, 3)).is_equal_to("1, 2, 3")
    assert_that(builder._fmt_args_kwargs("a", "b", "c")).is_equal_to("'a', 'b', 'c'")


def test_fmt_args_kwargs_single_kwarg():
    builder = assert_that(None)
    assert_that(builder._fmt_args_kwargs(a=1)).is_equal_to("'a': 1")
    assert_that(builder._fmt_args_kwargs(f="foo")).is_equal_to("'f': 'foo'")


def test_fmt_args_kwargs_multiple_kwargs():
    builder = assert_that(None)
    assert_that(builder._fmt_args_kwargs(a=1, b=2, c=3)).is_equal_to("'a': 1, 'b': 2, 'c': 3")
    assert_that(builder._fmt_args_kwargs(a="a", b="b", c="c")).is_equal_to("'a': 'a', 'b': 'b', 'c': 'c'")


def test_fmt_args_kwargs_multiple_both():
    builder = assert_that(None)
    assert_that(builder._fmt_args_kwargs(1, 2, 3, a=4, b=5, c=6)).is_equal_to("1, 2, 3, 'a': 4, 'b': 5, 'c': 6")
    assert_that(builder._fmt_args_kwargs("a", "b", "c", d="g", e="h", f="i")).is_equal_to(
        "'a', 'b', 'c', 'd': 'g', 'e': 'h', 'f': 'i'"
    )


def test_check_dict_like_empty_dict():
    builder = assert_that(None)
    assert_that(builder._require_dict_like({}))


def test_check_dict_like_not_iterable():
    builder = assert_that(None)
    assert_that(builder._require_dict_like).raises(TypeError).when_called_with(123).is_equal_to(
        "val <int> is not dict-like: not iterable"
    )


def test_check_dict_like_missing_keys():
    builder = assert_that(None)
    assert_that(builder._require_dict_like).raises(TypeError).when_called_with("foo").is_equal_to(
        "val <str> is not dict-like: missing keys()"
    )


def test_check_dict_like_bool():
    builder = assert_that(None)
    assert_that(builder._is_dict_like({})).is_true()
    assert_that(builder._is_dict_like(123)).is_false()
    assert_that(builder._is_dict_like("foo")).is_false()
