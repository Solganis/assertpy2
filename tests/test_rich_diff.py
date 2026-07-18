import subprocess
from collections import namedtuple
from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from assertpy2 import assert_that, match
from assertpy2._engine._diff import _build_equality_diff, _sub_diff_entries
from assertpy2.errors import DiffEntry, DiffResult
from assertpy2.helpers import HelpersMixin
from assertpy2.pytest_plugin import _format_diff


class TestBuildEqualityDiffSequence:
    def test_lists_equal_length_one_diff(self):
        result = _build_equality_diff([1, 2, 3], [1, 9, 3])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1]")
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_equal_to(9)

    def test_actual_longer(self):
        result = _build_equality_diff([1, 2, 3], [1])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_none()
        assert_that(result.entries[1].actual).is_equal_to(3)
        assert_that(result.entries[1].expected).is_none()

    def test_expected_longer(self):
        result = _build_equality_diff([1], [1, 2, 3])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to(2)

    def test_tuples(self):
        result = _build_equality_diff((1, 2), (1, 3))
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1]")

    def test_all_different(self):
        result = _build_equality_diff([1, 2], [3, 4])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)

    def test_empty_vs_nonempty(self):
        result = _build_equality_diff([], [1, 2])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to(1)


class TestBuildEqualityDiffSet:
    def test_extra_items(self):
        result = _build_equality_diff({1, 2, 3}, {1})
        assert_that(result.kind).is_equal_to("set")
        extra = [entry for entry in result.entries if entry.path == "extra"]
        assert_that(extra).is_length(2)
        assert_that([entry.expected for entry in extra]).each(match.is_none())

    def test_missing_items(self):
        result = _build_equality_diff({1}, {1, 2, 3})
        assert_that(result.kind).is_equal_to("set")
        missing = [entry for entry in result.entries if entry.path == "missing"]
        assert_that(missing).is_length(2)
        assert_that([entry.actual for entry in missing]).each(match.is_none())

    def test_both_extra_and_missing(self):
        result = _build_equality_diff({1, 2}, {2, 3})
        assert_that(result.kind).is_equal_to("set")
        extra = [entry for entry in result.entries if entry.path == "extra"]
        missing = [entry for entry in result.entries if entry.path == "missing"]
        assert_that(extra).is_length(1)
        assert_that(extra[0].actual).is_equal_to(1)
        assert_that(missing).is_length(1)
        assert_that(missing[0].expected).is_equal_to(3)

    def test_frozenset(self):
        result = _build_equality_diff(frozenset({1, 2}), frozenset({2, 3}))
        assert_that(result.kind).is_equal_to("set")
        assert_that(result.entries).is_length(2)


class TestBuildEqualityDiffString:
    def test_single_line_diff(self):
        result = _build_equality_diff("hello", "world")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("line 1")
        assert_that(result.entries[0].actual).is_equal_to("hello")
        assert_that(result.entries[0].expected).is_equal_to("world")

    def test_multiline_one_changed(self):
        result = _build_equality_diff("a\nb\nc", "a\nX\nc")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("line 2")
        assert_that(result.entries[0].actual).is_equal_to("b")
        assert_that(result.entries[0].expected).is_equal_to("X")

    def test_actual_more_lines(self):
        result = _build_equality_diff("a\nb\nc", "a")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_equal_to("b")
        assert_that(result.entries[0].expected).is_none()

    def test_expected_more_lines(self):
        result = _build_equality_diff("a", "a\nb\nc")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to("b")

    def test_identical_content_different_object(self):
        left = "hello"
        right = "".join(["h", "e", "l", "l", "o"])
        result = _build_equality_diff(left, right)
        assert_that(result.kind).is_equal_to("string")
        assert_that([entry.path for entry in result.entries]).is_in([], ["."])


class TestBuildEqualityDiffScalar:
    def test_int(self):
        result = _build_equality_diff(1, 2)
        assert_that(result.kind).is_equal_to("scalar")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".")
        assert_that(result.entries[0].actual).is_equal_to(1)
        assert_that(result.entries[0].expected).is_equal_to(2)

    def test_mixed_types(self):
        result = _build_equality_diff(42, "forty-two")
        assert_that(result.kind).is_equal_to("scalar")
        assert_that(result.entries).is_length(1)

    def test_none_vs_value(self):
        result = _build_equality_diff(None, 42)
        assert_that(result.kind).is_equal_to("scalar")

    def test_bool(self):
        result = _build_equality_diff(True, False)
        assert_that(result.kind).is_equal_to("scalar")


class TestBuildEqualityDiffDataclass:
    def test_field_difference(self):
        @dataclass
        class User:
            name: str
            age: int

        result = _build_equality_diff(User("Alice", 30), User("Alice", 31))
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

        result = _build_equality_diff(Point(1, 2), Point(3, 4))
        assert_that(result.kind).is_equal_to("dataclass")
        assert_that(result.entries).is_length(2)

    def test_all_same(self):
        @dataclass
        class Item:
            name: str

        result = _build_equality_diff(Item("a"), Item("a"))
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

        result = _build_equality_diff(A(1, 2), B(1, 99))
        assert_that(result.kind).is_equal_to("dataclass")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".y")
        assert_that(paths).contains(".z")
        y_entry = next(entry for entry in result.entries if entry.path == ".y")
        z_entry = next(entry for entry in result.entries if entry.path == ".z")
        assert_that(y_entry.expected).is_none()
        assert_that(z_entry.actual).is_none()


class TestBuildEqualityDiffNamedtuple:
    def test_field_difference(self):
        Point = namedtuple("Point", ["x", "y"])
        result = _build_equality_diff(Point(1, 2), Point(1, 99))
        assert_that(result.kind).is_equal_to("namedtuple")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".y")
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_equal_to(99)

    def test_all_same(self):
        Point = namedtuple("Point", ["x", "y"])
        result = _build_equality_diff(Point(1, 2), Point(1, 2))
        assert_that(result.kind).is_equal_to("namedtuple")
        assert_that(result.entries).is_length(0)

    def test_different_types_with_fields(self):
        A = namedtuple("A", ["x", "y"])
        B = namedtuple("B", ["x", "z"])
        result = _build_equality_diff(A(1, 2), B(1, 99))
        assert_that(result.kind).is_equal_to("namedtuple")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".y")
        assert_that(paths).contains(".z")


class TestBuildEqualityDiffRecursive:
    def test_dict_in_list(self):
        actual = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        expected = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Robert"}]
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1].name")
        assert_that(result.entries[0].actual).is_equal_to("Bob")
        assert_that(result.entries[0].expected).is_equal_to("Robert")

    def test_dict_in_list_added_key(self):
        actual = [{"a": 1}]
        expected = [{"a": 1, "b": 2}]
        result = _build_equality_diff(actual, expected)
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
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1].value")
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_equal_to(99)

    def test_non_dict_elements_stay_flat(self):
        result = _build_equality_diff([1, "a"], [1, "b"])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1]")
        assert_that(result.entries[0].actual).is_equal_to("a")

    def test_recursive_dict_removed_key(self):
        actual = [{"a": 1, "b": 2}]
        expected = [{"a": 1}]
        result = _build_equality_diff(actual, expected)
        assert_that([entry.path for entry in result.entries]).contains("[0].b")


class TestContainsDiff:
    def test_contains_missing_items_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains(7, 9)
        exc = exc_info.value
        assert_that(getattr(exc, "diff", None)).is_not_none()
        assert_that(exc.diff.kind).is_equal_to("contains")
        missing = [entry for entry in exc.diff.entries if entry.path == "missing"]
        assert_that(missing).is_length(2)

    def test_contains_single_item_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).contains(9)
        exc = exc_info.value
        assert_that(getattr(exc, "diff", None)).is_not_none()
        assert_that(exc.diff.kind).is_equal_to("contains")
        missing = [entry for entry in exc.diff.entries if entry.path == "missing"]
        assert_that(missing).is_length(1)
        assert_that(missing[0].expected).is_equal_to(9)

    def test_contains_exactly_missing_and_extra(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(["a", "b", "c"]).contains_exactly("a", "c", "d")
        exc = exc_info.value
        assert_that(exc.diff.kind).is_equal_to("contains")
        extra = [entry for entry in exc.diff.entries if entry.path == "extra"]
        missing = [entry for entry in exc.diff.entries if entry.path == "missing"]
        assert_that(extra).is_length(1)
        assert_that(extra[0].actual).is_equal_to("b")
        assert_that(missing).is_length(1)
        assert_that(missing[0].expected).is_equal_to("d")

    def test_contains_only_reports_both_halves_at_once(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(["a", "b", "x"]).contains_only("a", "b", "c")
        exc = exc_info.value
        assert_that(str(exc)).contains("but did contain <x> and did not contain <c>.")
        assert_that(exc.diff.kind).is_equal_to("contains")
        assert_that([entry.actual for entry in exc.diff.entries if entry.path == "extra"]).is_equal_to(["x"])
        assert_that([entry.expected for entry in exc.diff.entries if entry.path == "missing"]).is_equal_to(["c"])

    def test_contains_only_keeps_the_single_fault_wording(self):
        # the compat guard: only the both-at-once case may change how the message reads
        with pytest.raises(AssertionError) as extra_info:
            assert_that(["a", "b", "x"]).contains_only("a", "b")
        assert_that(str(extra_info.value)).ends_with("to contain only <'a', 'b'>, but did contain <x>.")
        with pytest.raises(AssertionError) as missing_info:
            assert_that(["a", "b"]).contains_only("a", "b", "c")
        assert_that(str(missing_info.value)).ends_with("to contain only <'a', 'b', 'c'>, but did not contain <c>.")

    def test_contains_exactly_order_only_points_at_the_first_disagreeing_index(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_exactly(3, 2, 1)
        exc = exc_info.value
        assert_that(str(exc)).contains("Same items, but the order differs at index 0.")
        assert_that(exc.diff.kind).is_equal_to("sequence")
        assert_that(exc.diff.entries).is_length(1)
        assert_that(exc.diff.entries[0].path).is_equal_to("[0]")
        assert_that(exc.diff.entries[0].actual).is_equal_to(1)
        assert_that(exc.diff.entries[0].expected).is_equal_to(3)

    def test_contains_exactly_order_only_skips_the_matching_prefix(self):
        # the first index is the one worth naming, not index 0 by default
        with pytest.raises(AssertionError) as exc_info:
            assert_that(["GET", "POST", "PUT"]).contains_exactly("GET", "PUT", "POST")
        assert_that(str(exc_info.value)).contains("the order differs at index 1.")

    def test_contains_exactly_wrong_items_still_reports_extra_and_missing(self):
        # the guard: only an equal multiset may take the ordering path
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_exactly(1, 2, 4)
        exc = exc_info.value
        assert_that(str(exc)).does_not_contain("order differs")
        assert_that(exc.diff.kind).is_equal_to("contains")


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


class TestListMessageCollapse:
    def test_list_in_dict_collapses_to_changed_element(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"rows": [{"id": 1, "v": "x"}, {"id": 2, "v": "y"}, {"id": 3, "v": "z"}]}).is_equal_to(
                {"rows": [{"id": 1, "v": "x"}, {"id": 2, "v": "CHANGED"}, {"id": 3, "v": "z"}]}
            )
        msg = str(exc.value)
        assert_that(msg).contains("[.., {.., 'v': 'y'}]")
        assert_that(msg).does_not_contain("'id': 1").does_not_contain("'id': 3")

    def test_scalar_list_collapses(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2, 3, 4, 5]}).is_equal_to({"a": [1, 2, 999, 4, 5]})
        assert_that(str(exc.value)).contains("'a': [.., 3]")

    def test_tuple_renders_with_parens(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"t": (1, 2, 3)}).is_equal_to({"t": (1, 9, 3)})
        assert_that(str(exc.value)).contains("'t': (.., 2)")

    def test_nested_list_of_lists(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"m": [[1, 2], [3, 4]]}).is_equal_to({"m": [[1, 2], [3, 99]]})
        assert_that(str(exc.value)).contains("[.., [.., 4]]")

    def test_extra_element_shown(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2, 3]}).is_equal_to({"a": [1, 2]})
        assert_that(str(exc.value)).contains("'a': [.., 3]")

    def test_tolerance_mismatch_shows_element_as_leaf(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1.0, 2.0, 3.0]}).is_equal_to({"a": [1.0, 2.5, 3.0]}, tolerance=0.1)
        assert_that(str(exc.value)).contains("'a': [.., 2.0]")

    def test_pure_dict_message_unchanged(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"user": {"id": 1, "zip": "10001"}}).is_equal_to({"user": {"id": 1, "zip": "99999"}})
        assert_that(str(exc.value)).contains("{.., 'zip': '10001'}")

    def test_self_referential_list_is_guarded(self):
        circular = [1]
        circular.append(circular)  # a list containing itself
        with pytest.raises(AssertionError) as exc:
            assert_that({"x": circular}).is_equal_to({"x": [1, [99]]})
        assert_that(str(exc.value)).contains("<circular ref>")

    def test_list_versus_dict_at_same_key_renders_without_crash(self):
        # a list on one side and a mapping on the other at the same key must not be routed through the
        # list collapser (which would index the mapping by position and raise); it renders as a plain leaf
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2]}).is_equal_to({"a": {"x": 1}})
        assert_that(str(exc.value)).contains("'a': [1, 2]")

    def test_fully_differing_list_has_no_ellipsis(self):
        # nothing collapses (every element differs) -> no ".." prefix should be added
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2]}).is_equal_to({"a": [9, 8]})
        assert_that(str(exc.value)).contains("'a': [1, 2]").does_not_contain("..")

    def test_multiple_extra_elements_are_all_shown(self):
        # more than one trailing element beyond the counterpart's length -> all of them shown, not just the first
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2, 3, 4]}).is_equal_to({"a": [1, 2]})
        assert_that(str(exc.value)).contains("[.., 3, 4]")


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


class TestStringDiffCarets:
    """String diffs point at the intra-line change with difflib carets instead of dumping whole lines."""

    def test_carets_mark_the_changed_span(self):
        diff = DiffResult(
            kind="string",
            entries=[DiffEntry(path="line 1", actual="the quick fox", expected="the quick cat")],
        )
        output = _format_diff(diff)
        assert_that(output).contains("- the quick fox")
        assert_that(output).contains("+ the quick cat")
        assert_that(output).contains("^")  # the ndiff caret guide row

    def test_long_lines_skip_the_carets(self):
        diff = DiffResult(
            kind="string",
            entries=[DiffEntry(path="line 1", actual="a" * 300, expected="b" * 300)],
        )
        output = _format_diff(diff)
        assert_that(output).contains("- 'aaa")
        assert_that(output).contains("+ 'bbb")
        assert_that(output).does_not_contain("^")

    def test_removed_line_renders_minus_only(self):
        diff = DiffResult(kind="string", entries=[DiffEntry(path="line 2", actual="gone", expected=None)])
        assert_that(_format_diff(diff)).contains("line 2: - 'gone'")

    def test_added_line_renders_plus_only(self):
        diff = DiffResult(kind="string", entries=[DiffEntry(path="line 2", actual=None, expected="new")])
        assert_that(_format_diff(diff)).contains("line 2: + 'new'")


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

    def test_matches_structure_diff_in_report(self, tmp_path):
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "from assertpy2 import assert_that, match\n"
            "def test_structure():\n"
            "    assert_that({'role': 'guest', 'address': {'city': 'LA'}}).matches_structure({\n"
            "        'role': match.is_in('admin', 'user'),\n"
            "        'address': match.structure({'city': match.equal_to('NYC')}),\n"
            "    })\n",
        )
        result = subprocess.run(
            ["uv", "run", "pytest", str(test_file), "-v", "--no-header", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert_that(result.stdout).contains("diff (match)")
        assert_that(result.stdout).contains("address.city")


class TestFormatDiffMatchKind:
    def test_renders_predicate_and_actual(self):
        diff = DiffResult(
            kind="match",
            entries=[DiffEntry(path="role", actual="guest", expected="a value in <('admin', 'user')>")],
        )
        output = _format_diff(diff)
        assert_that(output).contains("diff (match):")
        assert_that(output).contains("role: expected a value in <('admin', 'user')>, but was 'guest'")


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


class TestNestedDataclassDiff:
    def test_nested_dataclass_fields_expanded(self):
        @dataclass
        class Address:
            city: str
            zip_code: str

        @dataclass
        class User:
            name: str
            address: Address

        actual = User("Alice", Address("NYC", "10001"))
        expected = User("Alice", Address("LA", "90210"))
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("dataclass")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".address.city")
        assert_that(paths).contains(".address.zip_code")
        assert_that(paths).does_not_contain(".address")

    def test_nested_dataclass_mixed_fields(self):
        @dataclass
        class Inner:
            x: int
            y: int

        @dataclass
        class Outer:
            name: str
            inner: Inner

        actual = Outer("a", Inner(1, 2))
        expected = Outer("b", Inner(1, 3))
        result = _build_equality_diff(actual, expected)
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".name")
        assert_that(paths).contains(".inner.y")
        assert_that(paths).does_not_contain(".inner.x")

    def test_deeply_nested_dataclass(self):
        @dataclass
        class Level3:
            value: int

        @dataclass
        class Level2:
            child: Level3

        @dataclass
        class Level1:
            child: Level2

        actual = Level1(Level2(Level3(1)))
        expected = Level1(Level2(Level3(99)))
        result = _build_equality_diff(actual, expected)
        paths = [entry.path for entry in result.entries]
        assert_that(paths).is_equal_to([".child.child.value"])
        assert_that(result.entries[0].actual).is_equal_to(1)
        assert_that(result.entries[0].expected).is_equal_to(99)

    def test_nested_namedtuple_fields_expanded(self):
        Inner = namedtuple("Inner", ["a", "b"])
        Outer = namedtuple("Outer", ["name", "inner"])
        actual = Outer("same", Inner(1, 2))
        expected = Outer("same", Inner(1, 99))
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("namedtuple")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".inner.b")
        assert_that(paths).does_not_contain(".inner")

    def test_nested_dict_inside_dataclass_expanded(self):
        @dataclass
        class Config:
            name: str
            settings: dict

        actual = Config("app", {"debug": True, "port": 8080})
        expected = Config("app", {"debug": False, "port": 8080})
        result = _build_equality_diff(actual, expected)
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".settings.debug")

    def test_list_of_nested_dataclasses(self):
        @dataclass
        class Inner:
            value: int

        @dataclass
        class Wrapper:
            inner: Inner

        actual = [Wrapper(Inner(1)), Wrapper(Inner(2))]
        expected = [Wrapper(Inner(1)), Wrapper(Inner(99))]
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains("[1].inner.value")


class TestPydanticDiff:
    def test_pydantic_model_field_diff(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class UserModel(BaseModel):
            name: str
            age: int

        result = _build_equality_diff(UserModel(name="Alice", age=30), UserModel(name="Bob", age=30))
        assert_that(result.kind).is_equal_to("model")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".name")
        assert_that(result.entries[0].actual).is_equal_to("Alice")
        assert_that(result.entries[0].expected).is_equal_to("Bob")

    def test_nested_pydantic_model_diff(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class AddressModel(BaseModel):
            city: str
            zip_code: str

        class UserModel(BaseModel):
            name: str
            address: AddressModel

        actual = UserModel(name="Alice", address=AddressModel(city="NYC", zip_code="10001"))
        expected = UserModel(name="Alice", address=AddressModel(city="LA", zip_code="90210"))
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("model")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".address.city")
        assert_that(paths).contains(".address.zip_code")

    def test_pydantic_is_equal_to_without_filter(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Item(BaseModel):
            sku: str
            price: float

        with pytest.raises(AssertionError) as exc_info:
            assert_that(Item(sku="A", price=10.0)).is_equal_to(Item(sku="A", price=20.0))
        exc = exc_info.value
        assert_that(getattr(exc, "diff", None)).is_not_none()
        assert_that(exc.diff.kind).is_equal_to("model")
        assert_that(exc.diff.entries[0].path).is_equal_to(".price")

    def test_pydantic_in_list_diff(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            qty: int

        actual = [Item(name="A", qty=1), Item(name="B", qty=2)]
        expected = [Item(name="A", qty=1), Item(name="B", qty=99)]
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains("[1].qty")

    def test_pydantic_format_diff_renders(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Simple(BaseModel):
            x: int

        result = _build_equality_diff(Simple(x=1), Simple(x=2))
        output = _format_diff(result)
        assert_that(output).contains("diff (model):")
        assert_that(output).contains(".x:")


class TestModelDumpDiff:
    """Tests for model_dump() duck-type diff (covers Pydantic path without pydantic dep)."""

    def test_model_dump_field_diff(self):
        class FakeModel:
            def __init__(self, x, y):
                self._x = x
                self._y = y

            def model_dump(self):
                return {"x": self._x, "y": self._y}

            def __eq__(self, other):
                return isinstance(other, FakeModel) and self.model_dump() == other.model_dump()

        result = _build_equality_diff(FakeModel(1, 2), FakeModel(1, 99))
        assert_that(result.kind).is_equal_to("model")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".y")

    def test_model_dump_extra_key(self):
        class ModelA:
            def model_dump(self):
                return {"x": 1, "y": 2}

            def __eq__(self, other):
                return False

        class ModelB:
            def model_dump(self):
                return {"x": 1}

            def __eq__(self, other):
                return False

        result = _build_equality_diff(ModelA(), ModelB())
        assert_that(result.kind).is_equal_to("model")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".y")
        entry = next(entry for entry in result.entries if entry.path == ".y")
        assert_that(entry.expected).is_none()
        assert_that(entry.actual).is_equal_to(2)

    def test_model_dump_missing_key(self):
        class ModelA:
            def model_dump(self):
                return {"x": 1}

            def __eq__(self, other):
                return False

        class ModelB:
            def model_dump(self):
                return {"x": 1, "z": 3}

            def __eq__(self, other):
                return False

        result = _build_equality_diff(ModelA(), ModelB())
        entry = next(entry for entry in result.entries if entry.path == ".z")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_equal_to(3)

    def test_model_dump_nested_dict_in_sub_diff(self):
        class Outer:
            def model_dump(self):
                return {"nested": {"a": 1, "b": 2}}

            def __eq__(self, other):
                return False

        class Outer2:
            def model_dump(self):
                return {"nested": {"a": 1, "b": 99}}

            def __eq__(self, other):
                return False

        result = _build_equality_diff(Outer(), Outer2())
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".nested.b")

    def test_model_dump_scalar_field_in_sub_diff(self):
        class Outer:
            def model_dump(self):
                return {"val": 10}

            def __eq__(self, other):
                return False

        class Outer2:
            def model_dump(self):
                return {"val": 20}

            def __eq__(self, other):
                return False

        result = _sub_diff_entries(Outer(), Outer2(), "root")
        assert_that(result).is_not_none()
        assert_that(result[0].path).is_equal_to("root.val")

    def test_model_dump_in_sub_diff_extra_key(self):
        class ModelA:
            def model_dump(self):
                return {"x": 1, "y": 2}

            def __eq__(self, other):
                return False

        class ModelB:
            def model_dump(self):
                return {"x": 1}

            def __eq__(self, other):
                return False

        result = _sub_diff_entries(ModelA(), ModelB(), "item")
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "item.y")
        assert_that(entry.expected).is_none()

    def test_model_dump_in_sub_diff_missing_key(self):
        class ModelA:
            def model_dump(self):
                return {"x": 1}

            def __eq__(self, other):
                return False

        class ModelB:
            def model_dump(self):
                return {"x": 1, "z": 3}

            def __eq__(self, other):
                return False

        result = _sub_diff_entries(ModelA(), ModelB(), "item")
        entry = next(entry for entry in result if entry.path == "item.z")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_equal_to(3)

    def test_model_dump_in_sub_diff_nested_recurse(self):
        class Inner:
            def model_dump(self):
                return {"val": 42}

            def __eq__(self, other):
                return False

        class Outer:
            def model_dump(self):
                return {"child": {"val": 42}}

            def __eq__(self, other):
                return False

        class Outer2:
            def model_dump(self):
                return {"child": {"val": 99}}

            def __eq__(self, other):
                return False

        result = _sub_diff_entries(Outer(), Outer2(), "root")
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.child.val")


class TestSubDiffNamedtupleCoverage:
    def test_namedtuple_in_sub_diff_extra_field(self):
        A = namedtuple("A", ["x", "y"])
        B = namedtuple("B", ["x"])
        result = _sub_diff_entries(A(1, 2), B(1), "item")
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "item.y")
        assert_that(entry.expected).is_none()

    def test_namedtuple_in_sub_diff_missing_field(self):
        A = namedtuple("A", ["x"])
        B = namedtuple("B", ["x", "z"])
        result = _sub_diff_entries(A(1), B(1, 3), "item")
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "item.z")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_equal_to(3)

    def test_namedtuple_missing_field_sentinel(self):
        A = namedtuple("A", ["x", "y"])
        B = namedtuple("B", ["x"])
        result = _sub_diff_entries(A(1, 2), B(1), "root")
        assert_that(result).is_not_none()
        has_y = any(entry.path == "root.y" and entry.expected is None for entry in result)
        assert_that(has_y).is_true()

    def test_namedtuple_nested_recurse_in_sub_diff(self):
        Inner = namedtuple("Inner", ["a", "b"])
        Outer = namedtuple("Outer", ["name", "inner"])
        actual = Outer("same", Inner(1, 2))
        expected = Outer("same", Inner(1, 99))
        result = _sub_diff_entries(actual, expected, "root")
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.inner.b")

    def test_namedtuple_scalar_diff_in_sub_diff(self):
        Point = namedtuple("Point", ["x", "y"])
        result = _sub_diff_entries(Point(1, 2), Point(1, 99), "item")
        assert_that(result).is_not_none()
        assert_that(result[0].path).is_equal_to("item.y")
        assert_that(result[0].actual).is_equal_to(2)
        assert_that(result[0].expected).is_equal_to(99)


class TestBuildEqualityDiffCircularRef:
    def test_circular_ref_in_build_equality_diff(self):
        mapping = {"x": 1}
        result = _build_equality_diff(mapping, mapping, _seen={id(mapping)})
        assert_that(result.kind).is_equal_to("scalar")
        assert_that(result.entries[0].actual).is_equal_to("<circular ref>")

    def test_seen_passed_through(self):
        result = _build_equality_diff([1, 2], [1, 3], _seen=set())
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)


class TestSubDiffDataclassMissingField:
    def test_dataclass_missing_field_in_sub_diff(self):
        @dataclass
        class A:
            x: int
            y: int

        @dataclass
        class B:
            x: int

        result = _sub_diff_entries(A(1, 2), B(1), "root")
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "root.y")
        assert_that(entry.expected).is_none()

    def test_dataclass_nested_recurse_in_sub_diff(self):
        @dataclass
        class Inner:
            val: int

        @dataclass
        class Outer:
            inner: Inner

        result = _sub_diff_entries(Outer(Inner(1)), Outer(Inner(99)), "root")
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.inner.val")


class TestCircularRefProtection:
    def test_circular_dict_does_not_recurse_infinitely(self):
        left = {"x": 1}
        left["self"] = left
        right = {"x": 2, "self": "nope"}
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)

    def test_circular_dict_in_sub_diff(self):
        inner_a = {"val": 1}
        inner_a["loop"] = inner_a
        inner_b = {"val": 2}
        inner_b["loop"] = inner_b
        result = _sub_diff_entries(inner_a, inner_b, "root")
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.val")
        has_circular = any("circular" in str(entry.actual) or "circular" in str(entry.expected) for entry in result)
        assert_that(has_circular).is_true()

    def test_asymmetric_circular_ref_in_sub_diff(self):
        # Only the actual side loops; the expected side is a fresh, non-circular dict at the same key.
        # At that recursion only actual's id is in `seen`, so the cycle guard must fire on EITHER side
        # being seen (its `or`), not both - otherwise it recurses past the cycle and decomposes it.
        actual = {"name": "x"}
        actual["ref"] = actual
        expected = {"name": "y", "ref": {"name": "z"}}
        result = _sub_diff_entries(actual, expected, "root")
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.ref")
        entry = next(entry for entry in result if entry.path == "root.ref")
        assert_that(entry.actual).is_equal_to("<circular ref>")

    def test_circular_list_item_in_diff(self):
        inner_a = {"val": 1}
        inner_a["self"] = inner_a
        inner_b = {"val": 2}
        inner_b["self"] = inner_b
        result = _build_equality_diff([inner_a], [inner_b])
        assert_that(result.kind).is_equal_to("sequence")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains("[0].val")
        has_circular = any(
            "circular" in str(entry.actual) or "circular" in str(entry.expected) for entry in result.entries
        )
        assert_that(has_circular).is_true()

    def test_circular_in_dict_err(self):
        actual = {"a": 1}
        actual["self"] = actual
        expected = {"a": 2}
        expected["self"] = expected
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = getattr(exc_info.value, "diff", None)
        assert_that(diff).is_not_none()
        has_circular = any(
            "circular" in str(entry.actual) or "circular" in str(entry.expected) for entry in diff.entries
        )
        assert_that(has_circular).is_true()

    def test_mutual_circular_ref(self):
        left = {"key": "a_val"}
        right = {"key": "b_val"}
        left["ref"] = right
        right["ref"] = left
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to({"key": "other", "ref": {"key": "other2", "ref": "x"}})


class TestDictListValueDiff:
    def test_list_values_in_dict_are_expanded(self):
        actual = {"items": [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 1}]}
        expected = {"items": [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 3}]}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        assert_that(diff).is_not_none()
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("items[1].qty")

    def test_list_of_scalars_in_dict(self):
        actual = {"tags": [1, 2, 3]}
        expected = {"tags": [1, 2, 99]}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("tags[2]")

    def test_nested_dict_with_list_of_dicts(self):
        actual = {"config": {"rules": [{"name": "r1", "active": True}, {"name": "r2", "active": False}]}}
        expected = {"config": {"rules": [{"name": "r1", "active": True}, {"name": "r2", "active": True}]}}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("config.rules[1].active")

    def test_list_length_mismatch_in_dict(self):
        actual = {"items": [1, 2]}
        expected = {"items": [1, 2, 3]}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("items[2]")

    def test_actual_list_longer_in_dict(self):
        actual = {"items": [1, 2, 3]}
        expected = {"items": [1, 2]}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("items[2]")
        entry = next(entry for entry in diff.entries if entry.path == "items[2]")
        assert_that(entry.actual).is_equal_to(3)
        assert_that(entry.expected).is_none()


class _ReadOnlyMapping(Mapping):
    """A dict-like that is not a ``dict`` subclass, to exercise the duck mapping-like diff path."""

    def __init__(self, data):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __eq__(self, other):
        return isinstance(other, _ReadOnlyMapping) and self._data == other._data

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return f"_ReadOnlyMapping({self._data!r})"


class TestDiffEngineHarmonization:
    """The dict path and the base path share one nested diff engine (``_sub_diff_entries``).

    A nested non-dict structure (dataclass, model, namedtuple, list-of-lists, mapping) is therefore
    decomposed to its differing path inside a dict exactly as it already was inside a list, and the
    key ordering is repr-stable on both sides so mixed-type keys no longer raise.
    """

    @staticmethod
    def _diff_of(actual, expected, **kwargs):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected, **kwargs)
        return exc_info.value.diff

    def _paths(self, actual, expected, **kwargs):
        return [entry.path for entry in self._diff_of(actual, expected, **kwargs).entries]

    def test_dict_with_dataclass_value_decomposes(self):
        @dataclass
        class Point:
            x: int
            y: int

        assert_that(self._paths({"p": Point(1, 2)}, {"p": Point(1, 3)})).contains("p.y")

    def test_dict_with_model_value_decomposes(self):
        class FakeModel:
            def __init__(self, **fields):
                self.__dict__.update(fields)

            def model_dump(self):
                return dict(self.__dict__)

            def __eq__(self, other):
                return isinstance(other, FakeModel) and self.model_dump() == other.model_dump()

        assert_that(self._paths({"u": FakeModel(a=1, b=2)}, {"u": FakeModel(a=1, b=3)})).contains("u.b")

    def test_dict_with_namedtuple_value_uses_field_name(self):
        Pair = namedtuple("Pair", ["a", "b"])
        paths = self._paths({"p": Pair(1, 2)}, {"p": Pair(1, 3)})
        assert_that(paths).contains("p.b")
        assert_that(paths).does_not_contain("p[1]")

    def test_dict_with_list_of_lists_decomposes(self):
        assert_that(self._paths({"m": [[1, 2]]}, {"m": [[1, 9]]})).contains("m[0][1]")

    def test_list_with_mapping_value_decomposes(self):
        paths = self._paths([_ReadOnlyMapping({"a": 1})], [_ReadOnlyMapping({"a": 2})])
        assert_that(paths).contains("[0].a")

    def test_deep_crossover_dict_list_dict_dataclass(self):
        @dataclass
        class Point:
            x: int
            y: int

        actual = {"users": [{"profile": Point(1, 2)}]}
        expected = {"users": [{"profile": Point(1, 3)}]}
        assert_that(self._paths(actual, expected)).contains("users[0].profile.y")

    def test_mixed_type_keys_do_not_raise(self):
        diff = self._diff_of({1: "a", "b": 2}, {1: "z", "b": 2})
        assert_that([entry.path for entry in diff.entries]).contains("1")
        entry = next(entry for entry in diff.entries if entry.path == "1")
        assert_that(entry.actual).is_equal_to("a")
        assert_that(entry.expected).is_equal_to("z")

    def test_int_keys_sorted_by_repr(self):
        paths = self._paths({1: "a", 2: "b", 10: "c"}, {1: "z", 2: "y", 10: "x"})
        assert_that(paths).is_equal_to(["1", "10", "2"])

    def test_top_level_mapping_still_decomposes(self):
        paths = self._paths(_ReadOnlyMapping({"a": 1, "b": 2}), _ReadOnlyMapping({"a": 1, "b": 9}))
        assert_that(paths).is_equal_to(["b"])

    def test_mapping_value_in_dict_still_decomposes(self):
        actual = {"u": _ReadOnlyMapping({"a": 1, "b": 2})}
        expected = {"u": _ReadOnlyMapping({"a": 1, "b": 9})}
        assert_that(self._paths(actual, expected)).contains("u.b")


class TestDictCircularRefNotEqual:
    def test_circular_dict_not_equal_returns_false(self):
        mapping = {"x": 1}
        mapping["self"] = mapping
        mixin = type("M", (HelpersMixin,), {"val": None, "description": "", "kind": None, "expected": None})()
        result = mixin._dict_not_equal(mapping, mapping, _seen={(id(mapping), id(mapping))})
        assert_that(result).is_false()


class TestDiffOrderingActualGreater:
    """The field/element diff must report a difference when actual is greater than expected.

    Each case has a differing slot where actual > expected, and the diff must still surface it. The
    symmetric actual < expected direction is already covered by the diff tests above.
    """

    def test_build_namedtuple_actual_greater(self):
        Point = namedtuple("Point", ["x", "y"])
        result = _build_equality_diff(Point(1, 9), Point(1, 2))
        entry = next(entry for entry in result.entries if entry.path == ".y")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_build_dataclass_actual_greater(self):
        @dataclass
        class Dc:
            a: int
            b: int

        result = _build_equality_diff(Dc(1, 9), Dc(1, 2))
        entry = next(entry for entry in result.entries if entry.path == ".b")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_build_model_actual_greater(self):
        class FakeModel:
            def __init__(self, **fields):
                self.__dict__.update(fields)

            def model_dump(self):
                return dict(self.__dict__)

        result = _build_equality_diff(FakeModel(a=1, b=9), FakeModel(a=1, b=2))
        entry = next(entry for entry in result.entries if entry.path == ".b")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_build_sequence_actual_greater(self):
        result = _build_equality_diff([1, 9, 3], [1, 2, 3])
        entry = next(entry for entry in result.entries if entry.path == "[1]")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_build_string_actual_greater_line(self):
        result = _build_equality_diff("a\nz\nc", "a\nb\nc")
        entry = next(entry for entry in result.entries if entry.path == "line 2")
        assert_that(entry.actual).is_equal_to("z")
        assert_that(entry.expected).is_equal_to("b")

    def test_sub_dict_actual_greater(self):
        result = _sub_diff_entries({"k": 9}, {"k": 2}, "root")
        entry = next(entry for entry in result if entry.path == "root.k")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_sub_dataclass_actual_greater(self):
        @dataclass
        class Dc:
            a: int

        result = _sub_diff_entries(Dc(9), Dc(2), "root")
        entry = next(entry for entry in result if entry.path == "root.a")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_sub_namedtuple_actual_greater(self):
        Pair = namedtuple("Pair", ["x"])
        result = _sub_diff_entries(Pair(9), Pair(2), "root")
        entry = next(entry for entry in result if entry.path == "root.x")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_sub_model_actual_greater(self):
        class FakeModel:
            def __init__(self, **fields):
                self.__dict__.update(fields)

            def model_dump(self):
                return dict(self.__dict__)

        result = _sub_diff_entries(FakeModel(a=9), FakeModel(a=2), "root")
        entry = next(entry for entry in result if entry.path == "root.a")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)


class TestNestedSubDiffDecomposition:
    """Nested diffs (_sub_diff_entries) decompose sequences and report dataclass fields fully, matching
    the top-level _build_equality_diff. The nested-completeness feature; sets/strings stay leaves."""

    def test_nested_list_in_dataclass_decomposes(self):
        @dataclass
        class Box:
            items: list

        result = _build_equality_diff(Box([1, 2, 3]), Box([1, 9, 3]))
        entry = next(entry for entry in result.entries if entry.path == ".items[1]")
        assert_that(entry.actual).is_equal_to(2)
        assert_that(entry.expected).is_equal_to(9)

    def test_nested_list_in_model_decomposes(self):
        class FakeModel:
            def __init__(self, **fields):
                self.__dict__.update(fields)

            def model_dump(self):
                return dict(self.__dict__)

        result = _build_equality_diff(FakeModel(items=[1, 2]), FakeModel(items=[1, 9]))
        entry = next(entry for entry in result.entries if entry.path == ".items[1]")
        assert_that(entry.actual).is_equal_to(2)
        assert_that(entry.expected).is_equal_to(9)

    def test_sub_sequence_decomposes(self):
        result = _sub_diff_entries([1, 2, 3], [1, 9, 3], "root")
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "root[1]")
        assert_that(entry.actual).is_equal_to(2)
        assert_that(entry.expected).is_equal_to(9)

    def test_sub_dataclass_reports_expected_only_field(self):
        @dataclass
        class One:
            x: int

        @dataclass
        class Two:
            x: int
            y: int

        result = _sub_diff_entries(One(1), Two(1, 2), "root")
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "root.y")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_equal_to(2)

    def test_sub_dataclass_sorted_field_order(self):
        @dataclass
        class NonAlpha:
            z: int
            a: int

        result = _sub_diff_entries(NonAlpha(1, 1), NonAlpha(9, 9), "root")
        assert_that([entry.path for entry in result]).is_equal_to(["root.a", "root.z"])

    def test_nested_list_of_dataclass_in_dataclass_recurses(self):
        @dataclass
        class Inner:
            v: int

        @dataclass
        class Outer:
            items: list

        result = _build_equality_diff(Outer([Inner(1)]), Outer([Inner(9)]))
        entry = next(entry for entry in result.entries if entry.path == ".items[0].v")
        assert_that(entry.actual).is_equal_to(1)
        assert_that(entry.expected).is_equal_to(9)

    def test_nested_set_in_dataclass_stays_leaf(self):
        @dataclass
        class Box:
            tags: set

        result = _build_equality_diff(Box({1, 2}), Box({1, 9}))
        entry = next(entry for entry in result.entries if entry.path == ".tags")
        assert_that(entry.actual).is_equal_to({1, 2})
        assert_that(entry.expected).is_equal_to({1, 9})
