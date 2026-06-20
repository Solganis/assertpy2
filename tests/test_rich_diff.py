import subprocess
from collections import namedtuple
from dataclasses import dataclass

import pytest

from assertpy2 import assert_that, match
from assertpy2.base import BaseMixin
from assertpy2.errors import DiffEntry, DiffResult
from assertpy2.helpers import HelpersMixin
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
        extra = [entry for entry in result.entries if entry.path == "extra"]
        assert_that(extra).is_length(2)
        assert_that([entry.expected for entry in extra]).each(match.is_none())

    def test_missing_items(self):
        result = BaseMixin._build_equality_diff({1}, {1, 2, 3})
        assert_that(result.kind).is_equal_to("set")
        missing = [entry for entry in result.entries if entry.path == "missing"]
        assert_that(missing).is_length(2)
        assert_that([entry.actual for entry in missing]).each(match.is_none())

    def test_both_extra_and_missing(self):
        result = BaseMixin._build_equality_diff({1, 2}, {2, 3})
        assert_that(result.kind).is_equal_to("set")
        extra = [entry for entry in result.entries if entry.path == "extra"]
        missing = [entry for entry in result.entries if entry.path == "missing"]
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
        left = "hello"
        right = "".join(["h", "e", "l", "l", "o"])
        result = BaseMixin._build_equality_diff(left, right)
        assert_that(result.kind).is_equal_to("string")
        assert_that([entry.path for entry in result.entries]).is_in([], ["."])


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
        paths = [entry.path for entry in result.entries]
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

    def test_contains_single_item_no_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).contains(9)
        assert_that(getattr(exc_info.value, "diff", None)).is_none()

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
        result = BaseMixin._build_equality_diff(actual, expected)
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
        result = BaseMixin._build_equality_diff(actual, expected)
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
        result = BaseMixin._build_equality_diff(actual, expected)
        paths = [entry.path for entry in result.entries]
        assert_that(paths).is_equal_to([".child.child.value"])
        assert_that(result.entries[0].actual).is_equal_to(1)
        assert_that(result.entries[0].expected).is_equal_to(99)

    def test_nested_namedtuple_fields_expanded(self):
        Inner = namedtuple("Inner", ["a", "b"])
        Outer = namedtuple("Outer", ["name", "inner"])
        actual = Outer("same", Inner(1, 2))
        expected = Outer("same", Inner(1, 99))
        result = BaseMixin._build_equality_diff(actual, expected)
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
        result = BaseMixin._build_equality_diff(actual, expected)
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
        result = BaseMixin._build_equality_diff(actual, expected)
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

        result = BaseMixin._build_equality_diff(UserModel(name="Alice", age=30), UserModel(name="Bob", age=30))
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
        result = BaseMixin._build_equality_diff(actual, expected)
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
        result = BaseMixin._build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains("[1].qty")

    def test_pydantic_format_diff_renders(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Simple(BaseModel):
            x: int

        result = BaseMixin._build_equality_diff(Simple(x=1), Simple(x=2))
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

        result = BaseMixin._build_equality_diff(FakeModel(1, 2), FakeModel(1, 99))
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

        result = BaseMixin._build_equality_diff(ModelA(), ModelB())
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

        result = BaseMixin._build_equality_diff(ModelA(), ModelB())
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

        result = BaseMixin._build_equality_diff(Outer(), Outer2())
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

        result = BaseMixin._sub_diff_entries(Outer(), Outer2(), "root")
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

        result = BaseMixin._sub_diff_entries(ModelA(), ModelB(), "item")
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

        result = BaseMixin._sub_diff_entries(ModelA(), ModelB(), "item")
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

        result = BaseMixin._sub_diff_entries(Outer(), Outer2(), "root")
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.child.val")


class TestSubDiffNamedtupleCoverage:
    def test_namedtuple_in_sub_diff_extra_field(self):
        A = namedtuple("A", ["x", "y"])
        B = namedtuple("B", ["x"])
        result = BaseMixin._sub_diff_entries(A(1, 2), B(1), "item")
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "item.y")
        assert_that(entry.expected).is_none()

    def test_namedtuple_in_sub_diff_missing_field(self):
        A = namedtuple("A", ["x"])
        B = namedtuple("B", ["x", "z"])
        result = BaseMixin._sub_diff_entries(A(1), B(1, 3), "item")
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "item.z")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_equal_to(3)

    def test_namedtuple_missing_field_sentinel(self):
        A = namedtuple("A", ["x", "y"])
        B = namedtuple("B", ["x"])
        result = BaseMixin._sub_diff_entries(A(1, 2), B(1), "root")
        assert_that(result).is_not_none()
        has_y = any(entry.path == "root.y" and entry.expected is None for entry in result)
        assert_that(has_y).is_true()

    def test_namedtuple_nested_recurse_in_sub_diff(self):
        Inner = namedtuple("Inner", ["a", "b"])
        Outer = namedtuple("Outer", ["name", "inner"])
        actual = Outer("same", Inner(1, 2))
        expected = Outer("same", Inner(1, 99))
        result = BaseMixin._sub_diff_entries(actual, expected, "root")
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.inner.b")

    def test_namedtuple_scalar_diff_in_sub_diff(self):
        Point = namedtuple("Point", ["x", "y"])
        result = BaseMixin._sub_diff_entries(Point(1, 2), Point(1, 99), "item")
        assert_that(result).is_not_none()
        assert_that(result[0].path).is_equal_to("item.y")
        assert_that(result[0].actual).is_equal_to(2)
        assert_that(result[0].expected).is_equal_to(99)


class TestBuildEqualityDiffCircularRef:
    def test_circular_ref_in_build_equality_diff(self):
        mapping = {"x": 1}
        result = BaseMixin._build_equality_diff(mapping, mapping, _seen={id(mapping)})
        assert_that(result.kind).is_equal_to("scalar")
        assert_that(result.entries[0].actual).is_equal_to("<circular ref>")

    def test_seen_passed_through(self):
        result = BaseMixin._build_equality_diff([1, 2], [1, 3], _seen=set())
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

        result = BaseMixin._sub_diff_entries(A(1, 2), B(1), "root")
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

        result = BaseMixin._sub_diff_entries(Outer(Inner(1)), Outer(Inner(99)), "root")
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
        result = BaseMixin._sub_diff_entries(inner_a, inner_b, "root")
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.val")
        has_circular = any("circular" in str(entry.actual) or "circular" in str(entry.expected) for entry in result)
        assert_that(has_circular).is_true()

    def test_circular_list_item_in_diff(self):
        inner_a = {"val": 1}
        inner_a["self"] = inner_a
        inner_b = {"val": 2}
        inner_b["self"] = inner_b
        result = BaseMixin._build_equality_diff([inner_a], [inner_b])
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


class TestDictCircularRefNotEqual:
    def test_circular_dict_not_equal_returns_false(self):
        mapping = {"x": 1}
        mapping["self"] = mapping
        mixin = type("M", (HelpersMixin,), {"val": None, "description": "", "kind": None, "expected": None})()
        result = mixin._dict_not_equal(mapping, mapping, _seen={(id(mapping), id(mapping))})
        assert_that(result).is_false()
