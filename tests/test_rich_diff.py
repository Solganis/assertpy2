import subprocess
from collections import namedtuple
from dataclasses import dataclass

import pytest

from assertpy2 import assert_that, match
from assertpy2.base import BaseMixin
from assertpy2.errors import DiffEntry, DiffResult
from assertpy2.pytest_plugin import _format_diff


class TestBuildEqualityDiffSequence:
    def test_lists_equal_length_one_diff(self):
        result = BaseMixin._build_equality_diff([1, 2, 3], [1, 9, 3])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1]")
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_equal_to(9)

    def test_actual_longer(self):
        result = BaseMixin._build_equality_diff([1, 2, 3], [1])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_none()
        assert_that(result.entries[1].actual).is_equal_to(3)
        assert_that(result.entries[1].expected).is_none()

    def test_expected_longer(self):
        result = BaseMixin._build_equality_diff([1], [1, 2, 3])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to(2)

    def test_tuples(self):
        result = BaseMixin._build_equality_diff((1, 2), (1, 3))
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1]")

    def test_all_different(self):
        result = BaseMixin._build_equality_diff([1, 2], [3, 4])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)

    def test_empty_vs_nonempty(self):
        result = BaseMixin._build_equality_diff([], [1, 2])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to(1)


class TestBuildEqualityDiffSet:
    def test_extra_items(self):
        result = BaseMixin._build_equality_diff({1, 2, 3}, {1})
        assert_that(result.kind).is_equal_to("set")
        extra = [e for e in result.entries if e.path == "extra"]
        assert_that(extra).is_length(2)
        assert_that([e.expected for e in extra]).each(match.is_none())

    def test_missing_items(self):
        result = BaseMixin._build_equality_diff({1}, {1, 2, 3})
        assert_that(result.kind).is_equal_to("set")
        missing = [e for e in result.entries if e.path == "missing"]
        assert_that(missing).is_length(2)
        assert_that([e.actual for e in missing]).each(match.is_none())

    def test_both_extra_and_missing(self):
        result = BaseMixin._build_equality_diff({1, 2}, {2, 3})
        assert_that(result.kind).is_equal_to("set")
        extra = [e for e in result.entries if e.path == "extra"]
        missing = [e for e in result.entries if e.path == "missing"]
        assert_that(extra).is_length(1)
        assert_that(extra[0].actual).is_equal_to(1)
        assert_that(missing).is_length(1)
        assert_that(missing[0].expected).is_equal_to(3)

    def test_frozenset(self):
        result = BaseMixin._build_equality_diff(frozenset({1, 2}), frozenset({2, 3}))
        assert_that(result.kind).is_equal_to("set")
        assert_that(result.entries).is_length(2)


class TestBuildEqualityDiffString:
    def test_single_line_diff(self):
        result = BaseMixin._build_equality_diff("hello", "world")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("line 1")
        assert_that(result.entries[0].actual).is_equal_to("hello")
        assert_that(result.entries[0].expected).is_equal_to("world")

    def test_multiline_one_changed(self):
        result = BaseMixin._build_equality_diff("a\nb\nc", "a\nX\nc")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("line 2")
        assert_that(result.entries[0].actual).is_equal_to("b")
        assert_that(result.entries[0].expected).is_equal_to("X")

    def test_actual_more_lines(self):
        result = BaseMixin._build_equality_diff("a\nb\nc", "a")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_equal_to("b")
        assert_that(result.entries[0].expected).is_none()

    def test_expected_more_lines(self):
        result = BaseMixin._build_equality_diff("a", "a\nb\nc")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to("b")

    def test_identical_content_different_object(self):
        a = "hello"
        b = "".join(["h", "e", "l", "l", "o"])
        result = BaseMixin._build_equality_diff(a, b)
        assert_that(result.kind).is_equal_to("string")
        assert_that([e.path for e in result.entries]).is_in([], ["."])


class TestBuildEqualityDiffScalar:
    def test_int(self):
        result = BaseMixin._build_equality_diff(1, 2)
        assert_that(result.kind).is_equal_to("scalar")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".")
        assert_that(result.entries[0].actual).is_equal_to(1)
        assert_that(result.entries[0].expected).is_equal_to(2)

    def test_mixed_types(self):
        result = BaseMixin._build_equality_diff(42, "forty-two")
        assert_that(result.kind).is_equal_to("scalar")
        assert_that(result.entries).is_length(1)

    def test_none_vs_value(self):
        result = BaseMixin._build_equality_diff(None, 42)
        assert_that(result.kind).is_equal_to("scalar")

    def test_bool(self):
        result = BaseMixin._build_equality_diff(True, False)
        assert_that(result.kind).is_equal_to("scalar")


class TestBuildEqualityDiffDataclass:
    def test_field_difference(self):
        @dataclass
        class User:
            name: str
            age: int

        result = BaseMixin._build_equality_diff(User("Alice", 30), User("Alice", 31))
        assert_that(result.kind).is_equal_to("dataclass")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".age")
        assert_that(result.entries[0].actual).is_equal_to(30)
        assert_that(result.entries[0].expected).is_equal_to(31)

    def test_multiple_differences(self):
        @dataclass
        class Point:
            x: int
            y: int

        result = BaseMixin._build_equality_diff(Point(1, 2), Point(3, 4))
        assert_that(result.kind).is_equal_to("dataclass")
        assert_that(result.entries).is_length(2)

    def test_all_same(self):
        @dataclass
        class Item:
            name: str

        result = BaseMixin._build_equality_diff(Item("a"), Item("a"))
        assert_that(result.kind).is_equal_to("dataclass")
        assert_that(result.entries).is_length(0)

    def test_different_dataclass_types(self):
        @dataclass
        class A:
            x: int
            y: int

        @dataclass
        class B:
            x: int
            z: int

        result = BaseMixin._build_equality_diff(A(1, 2), B(1, 99))
        assert_that(result.kind).is_equal_to("dataclass")
        paths = [e.path for e in result.entries]
        assert_that(paths).contains(".y")
        assert_that(paths).contains(".z")
        y_entry = next(e for e in result.entries if e.path == ".y")
        z_entry = next(e for e in result.entries if e.path == ".z")
        assert_that(y_entry.expected).is_none()
        assert_that(z_entry.actual).is_none()


class TestBuildEqualityDiffNamedtuple:
    def test_field_difference(self):
        Point = namedtuple("Point", ["x", "y"])
        result = BaseMixin._build_equality_diff(Point(1, 2), Point(1, 99))
        assert_that(result.kind).is_equal_to("namedtuple")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".y")
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_equal_to(99)

    def test_all_same(self):
        Point = namedtuple("Point", ["x", "y"])
        result = BaseMixin._build_equality_diff(Point(1, 2), Point(1, 2))
        assert_that(result.kind).is_equal_to("namedtuple")
        assert_that(result.entries).is_length(0)

    def test_different_types_with_fields(self):
        A = namedtuple("A", ["x", "y"])
        B = namedtuple("B", ["x", "z"])
        result = BaseMixin._build_equality_diff(A(1, 2), B(1, 99))
        assert_that(result.kind).is_equal_to("namedtuple")
        paths = [e.path for e in result.entries]
        assert_that(paths).contains(".y")
        assert_that(paths).contains(".z")


class TestBuildEqualityDiffRecursive:
    def test_dict_in_list(self):
        actual = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        expected = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Robert"}]
        result = BaseMixin._build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1].name")
        assert_that(result.entries[0].actual).is_equal_to("Bob")
        assert_that(result.entries[0].expected).is_equal_to("Robert")

    def test_dict_in_list_added_key(self):
        actual = [{"a": 1}]
        expected = [{"a": 1, "b": 2}]
        result = BaseMixin._build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries[0].path).is_in("[1].b", "[0].b")
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to(2)

    def test_dataclass_in_list(self):
        @dataclass
        class Item:
            name: str
            value: int

        actual = [Item("x", 1), Item("y", 2)]
        expected = [Item("x", 1), Item("y", 99)]
        result = BaseMixin._build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1].value")
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_equal_to(99)

    def test_non_dict_elements_stay_flat(self):
        result = BaseMixin._build_equality_diff([1, "a"], [1, "b"])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1]")
        assert_that(result.entries[0].actual).is_equal_to("a")

    def test_recursive_dict_removed_key(self):
        actual = [{"a": 1, "b": 2}]
        expected = [{"a": 1}]
        result = BaseMixin._build_equality_diff(actual, expected)
        assert_that([e.path for e in result.entries]).contains("[0].b")


class TestContainsDiff:
    def test_contains_missing_items_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains(7, 9)
        exc = exc_info.value
        assert_that(getattr(exc, "diff", None)).is_not_none()
        assert_that(exc.diff.kind).is_equal_to("contains")
        missing = [e for e in exc.diff.entries if e.path == "missing"]
        assert_that(missing).is_length(2)

    def test_contains_single_item_no_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).contains(9)
        assert_that(getattr(exc_info.value, "diff", None)).is_none()

    def test_contains_exactly_missing_and_extra(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(["a", "b", "c"]).contains_exactly("a", "c", "d")
        exc = exc_info.value
        assert_that(exc.diff.kind).is_equal_to("contains")
        extra = [e for e in exc.diff.entries if e.path == "extra"]
        missing = [e for e in exc.diff.entries if e.path == "missing"]
        assert_that(extra).is_length(1)
        assert_that(extra[0].actual).is_equal_to("b")
        assert_that(missing).is_length(1)
        assert_that(missing[0].expected).is_equal_to("d")

    def test_contains_exactly_order_only_no_structured_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_exactly(3, 2, 1)
        assert_that(hasattr(exc_info.value, "diff")).is_false()


class TestIsEqualToWithDiff:
    def test_list_failure_includes_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).is_equal_to([1, 9, 3])
        exc = exc_info.value
        assert_that(getattr(exc, "diff", None)).is_not_none()
        assert_that(exc.diff.kind).is_equal_to("sequence")
        assert_that(exc.diff.entries).is_length(1)

    def test_set_failure_includes_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({1, 2}).is_equal_to({2, 3})
        assert_that(exc_info.value.diff.kind).is_equal_to("set")

    def test_string_failure_includes_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that("hello").is_equal_to("world")
        assert_that(exc_info.value.diff.kind).is_equal_to("string")

    def test_scalar_failure_includes_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(42).is_equal_to(99)
        assert_that(exc_info.value.diff.kind).is_equal_to("scalar")

    def test_success_no_exception(self):
        assert_that([1, 2, 3]).is_equal_to([1, 2, 3])
        assert_that({1, 2}).is_equal_to({1, 2})
        assert_that("hello").is_equal_to("hello")
        assert_that(42).is_equal_to(42)


class TestDiffResultStr:
    def test_empty_entries(self):
        diff = DiffResult(kind="scalar", entries=[])
        assert_that(str(diff)).is_equal_to("")

    def test_with_entries(self):
        diff = DiffResult(
            kind="sequence",
            entries=[DiffEntry(path="[0]", actual=1, expected=2)],
        )
        output = str(diff)
        assert_that(output).contains("diff (sequence):")
        assert_that(output).contains("[0]")

    def test_entry_str(self):
        entry = DiffEntry(path="[1]", actual="a", expected="b")
        assert_that(str(entry)).contains("at [1]")
        assert_that(str(entry)).contains("actual=<a>")
        assert_that(str(entry)).contains("expected=<b>")


class TestPytestPluginDiffRendering:
    def test_diff_appears_in_report(self, tmp_path):
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "from assertpy2 import assert_that\n"
            "def test_list_diff():\n"
            "    assert_that([1, 2, 3]).is_equal_to([1, 9, 3])\n",
        )
        result = subprocess.run(
            ["uv", "run", "pytest", str(test_file), "-v", "--no-header", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert_that(result.stdout).contains("AssertionFailure")
        assert_that(result.stdout).contains("Structured Diff")

    def test_scalar_diff_in_report(self, tmp_path):
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "from assertpy2 import assert_that\ndef test_scalar():\n    assert_that(42).is_equal_to(99)\n",
        )
        result = subprocess.run(
            ["uv", "run", "pytest", str(test_file), "-v", "--no-header", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert_that(result.stdout).contains("AssertionFailure")

    def test_diff_disabled_via_ini(self, tmp_path):
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "from assertpy2 import assert_that\ndef test_x():\n    assert_that([1]).is_equal_to([2])\n",
        )
        result = subprocess.run(
            ["uv", "run", "pytest", str(test_file), "-v", "--no-header", "--tb=short", "-o", "assertpy2_diff=off"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert_that(result.stdout).does_not_contain("Structured Diff")


class TestFormatDiffTruncation:
    def test_truncation_when_over_max(self):
        entries = [DiffEntry(path=f"[{i}]", actual=i, expected=i + 100) for i in range(10)]
        diff = DiffResult(kind="sequence", entries=entries)
        output = _format_diff(diff, max_entries=3)
        assert_that(output).contains("... and 7 more entries")

    def test_no_truncation_when_under_max(self):
        entries = [DiffEntry(path="[0]", actual=1, expected=2)]
        diff = DiffResult(kind="sequence", entries=entries)
        output = _format_diff(diff, max_entries=50)
        assert_that(output).does_not_contain("more entries")

    def test_no_truncation_when_zero(self):
        entries = [DiffEntry(path=f"[{i}]", actual=i, expected=i + 100) for i in range(100)]
        diff = DiffResult(kind="sequence", entries=entries)
        output = _format_diff(diff, max_entries=0)
        assert_that(output).does_not_contain("more entries")
        assert_that(output).contains("[99]")
