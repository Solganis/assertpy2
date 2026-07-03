import pytest

from assertpy2 import AssertionFailure, DiffEntry, DiffResult, assert_that, soft_assertions


class TestAssertionFailure:
    def test_is_subclass_of_assertion_error(self):
        assert_that(issubclass(AssertionFailure, AssertionError)).is_true()

    def test_caught_by_except_assertion_error(self):
        try:
            raise AssertionFailure("test message")
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to("test message")

    def test_message(self):
        err = AssertionFailure("something went wrong")
        assert_that(str(err)).is_equal_to("something went wrong")

    def test_actual_and_expected(self):
        err = AssertionFailure("msg", actual=1, expected=2)
        assert_that(err.actual).is_equal_to(1)
        assert_that(err.expected).is_equal_to(2)
        assert_that(err.diff).is_none()

    def test_actual_none(self):
        err = AssertionFailure("msg", actual=None, expected=42)
        assert_that(err.actual).is_none()
        assert_that(err.expected).is_equal_to(42)

    def test_diff(self):
        diff = DiffResult(
            kind="dict",
            entries=[DiffEntry(path="root.a", actual=1, expected=2)],
        )
        err = AssertionFailure("msg", actual={"a": 1}, expected={"a": 2}, diff=diff)
        assert_that(err.diff).is_not_none()
        assert_that(err.diff.kind).is_equal_to("dict")
        assert_that(err.diff.entries).is_length(1)

    def test_defaults(self):
        err = AssertionFailure("msg")
        assert_that(err.actual).is_none()
        assert_that(err.expected).is_none()
        assert_that(err.diff).is_none()


class TestDiffEntry:
    def test_str(self):
        entry = DiffEntry(path="root.a", actual=1, expected=2)
        assert_that(str(entry)).is_equal_to("  at root.a: actual=<1>, expected=<2>")

    def test_defaults(self):
        entry = DiffEntry(path="root")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_none()


class TestDiffResult:
    def test_str_empty(self):
        diff = DiffResult(kind="dict")
        assert_that(str(diff)).is_equal_to("")

    def test_str_with_entries(self):
        diff = DiffResult(
            kind="dict",
            entries=[
                DiffEntry(path="root.a", actual=1, expected=2),
                DiffEntry(path="root.b", actual="x", expected="y"),
            ],
        )
        result = str(diff)
        assert_that(result).starts_with("diff (dict):")
        assert_that(result).contains("at root.a")
        assert_that(result).contains("at root.b")


class TestStructuredErrorFromAssertions:
    def test_is_equal_to_raises_assertion_failure(self):
        try:
            assert_that(1).is_equal_to(2)
        except AssertionFailure as ex:
            assert_that(ex.actual).is_equal_to(1)
            assert_that(ex.expected).is_equal_to(2)
            assert_that(ex.diff).is_not_none()
            assert_that(ex.diff.kind).is_equal_to("scalar")
            assert_that(ex.diff.entries).is_length(1)
            assert_that(ex.diff.entries[0].path).is_equal_to(".")
            assert_that(ex.diff.entries[0].actual).is_equal_to(1)
            assert_that(ex.diff.entries[0].expected).is_equal_to(2)
        except AssertionError:
            raise AssertionError("expected AssertionFailure, got plain AssertionError") from None

    def test_is_equal_to_string_raises_assertion_failure(self):
        try:
            assert_that("foo").is_equal_to("bar")
        except AssertionFailure as ex:
            assert_that(ex.actual).is_equal_to("foo")
            assert_that(ex.expected).is_equal_to("bar")

    def test_is_equal_to_dict_raises_assertion_failure(self):
        try:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 3})
        except AssertionFailure as ex:
            assert_that(ex.actual).is_equal_to({"a": 1, "b": 2})
            assert_that(ex.expected).is_equal_to({"a": 1, "b": 3})
            assert_that(ex.diff).is_not_none()
            assert_that(ex.diff.kind).is_equal_to("dict")
            assert_that(ex.diff.entries).is_length(1)
            assert_that(ex.diff.entries[0].path).is_equal_to("b")
            assert_that(ex.diff.entries[0].actual).is_equal_to(2)
            assert_that(ex.diff.entries[0].expected).is_equal_to(3)

    def test_is_equal_to_dict_nested_diff(self):
        try:
            assert_that({"x": {"y": 1}}).is_equal_to({"x": {"y": 2}})
        except AssertionFailure as ex:
            assert_that(ex.diff).is_not_none()
            assert_that(ex.diff.entries).is_length(1)
            assert_that(ex.diff.entries[0].path).is_equal_to("x.y")

    def test_is_equal_to_dict_missing_keys_diff(self):
        try:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "c": 3})
        except AssertionFailure as ex:
            assert_that(ex.diff).is_not_none()
            paths = [entry.path for entry in ex.diff.entries]
            assert_that(paths).contains("b")
            assert_that(paths).contains("c")

    def test_is_equal_to_dict_with_ignore_raises_assertion_failure(self):
        try:
            assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 99}, ignore="c")
        except AssertionFailure as ex:
            assert_that(ex.actual).is_equal_to({"a": 1, "b": 2, "c": 3})
            assert_that(ex.expected).is_equal_to({"a": 1, "b": 99})

    def test_is_not_equal_to_raises_plain_assertion_error(self):
        try:
            assert_that(1).is_not_equal_to(1)
        except AssertionError as ex:
            assert_that(type(ex).__name__).is_equal_to("AssertionError")

    def test_is_true_raises_plain_assertion_error(self):
        try:
            assert_that(False).is_true()
        except AssertionError as ex:
            assert_that(type(ex).__name__).is_equal_to("AssertionError")

    def test_soft_assertions_still_work(self):
        try:
            with soft_assertions():
                assert_that(1).is_equal_to(2)
                assert_that("a").is_equal_to("b")
        except AssertionError as ex:
            assert_that(str(ex)).contains("1.")
            assert_that(str(ex)).contains("2.")

    def test_is_equal_to_pass_does_not_raise(self):
        assert_that(42).is_equal_to(42)
        assert_that("foo").is_equal_to("foo")
        assert_that({"a": 1}).is_equal_to({"a": 1})


class TestMessageTruncation:
    """Rendered failure text is capped; the structured payload always keeps the full data."""

    def test_huge_operand_repr_is_capped(self):
        huge = "x" * 10_000
        with pytest.raises(AssertionError) as exc_info:
            assert_that(huge).is_equal_to("y")
        message = str(exc_info.value)
        assert_that(len(message)).is_less_than(10_000)
        assert_that(message).contains("more chars")

    def test_is_not_equal_to_huge_operands_capped(self):
        huge = "x" * 10_000
        with pytest.raises(AssertionError) as exc_info:
            assert_that(huge).is_not_equal_to(huge)
        message = str(exc_info.value)
        assert_that(len(message)).is_less_than(10_000)
        assert_that(message).contains("more chars")

    def test_huge_dict_message_is_capped_but_payload_is_full(self):
        actual = {index: index for index in range(10_000)}
        expected = {index: index + 1 for index in range(10_000)}
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(actual).is_equal_to(expected)
        failure = exc_info.value
        assert_that(len(str(failure))).is_less_than(20_000)
        assert_that(failure.diff.entries).is_length(10_000)
        assert_that(failure.actual).is_length(10_000)

    def test_diff_str_renders_at_most_fifty_entries(self):
        entries = [DiffEntry(path=str(index), actual=index, expected=index + 1) for index in range(60)]
        rendered = str(DiffResult(kind="dict", entries=entries))
        assert_that(rendered).contains("... and 10 more entries")
        assert_that(rendered.splitlines()).is_length(52)

    def test_diff_str_at_fifty_entries_is_not_truncated(self):
        entries = [DiffEntry(path=str(index), actual=index, expected=index + 1) for index in range(50)]
        rendered = str(DiffResult(kind="dict", entries=entries))
        assert_that(rendered).does_not_contain("more entries")
        assert_that(rendered.splitlines()).is_length(51)

    def test_diff_entry_huge_leaf_is_capped(self):
        entry = DiffEntry(path="k", actual="x" * 10_000, expected="y")
        assert_that(len(str(entry))).is_less_than(6_000)
        assert_that(str(entry)).contains("more chars")
