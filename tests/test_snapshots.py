import collections
import contextlib
import datetime
import json
import os
import shutil
import sys
import threading
import time

import pytest

from assertpy2 import SnapshotCreatedWarning, assert_that, fail
from assertpy2.snapshot import _file_lock


# first pass re-captures every snapshot; the capture warnings themselves are pinned in
# TestSnapshotCreatedWarning, here they would only obscure the roundtrip
@pytest.mark.filterwarnings("ignore::assertpy2.snapshot.SnapshotCreatedWarning")
@pytest.mark.parametrize("count", [1, 2])
def test_snapshot_roundtrip_all_types(count):
    # test runs twice
    if count == 1:
        # on first pass, delete old snapshots...so they are re-created and saved
        if os.path.exists("__snapshots"):
            shutil.rmtree("__snapshots")
    if count == 2:
        # on second pass, snapshots are loaded and checked
        assert_that("__snapshots").exists().is_directory()

    assert_that(None).snapshot()

    assert_that(True).snapshot()
    assert_that(False).snapshot()

    assert_that(123).snapshot()
    assert_that(-456).snapshot()

    assert_that(123.456).snapshot()
    assert_that(-987.654).snapshot()

    assert_that("").snapshot()
    assert_that("foo").snapshot()

    assert_that([1, 2, 3]).snapshot()

    assert_that(["a", "b", "c"]).snapshot()

    assert_that([[1, 2, 3], ["a", "b", "c"]]).snapshot()

    assert_that({"a", "b", "c"}).snapshot()

    assert_that({"a": 1, "b": 2, "c": 3}).snapshot()

    assert_that({"a": {"x": 1}, "b": {"y": 2}, "c": {"z": 3}}).snapshot()

    assert_that({"a": [1, 2], "b": [3, 4], "c": [5, 6]}).snapshot()

    assert_that({"a": {1, 2}, "b": {3, 4}, "c": {5, 6}}).snapshot()

    assert_that({"a": {"b": {"c": {"x": {"y": {"z": 1}}}}}}).snapshot()

    assert_that(collections.OrderedDict([("a", 1), ("c", 3), ("b", 2)])).snapshot()

    assert_that(datetime.datetime(2000, 11, 22, 3, 44, 55)).snapshot()

    assert_that(1 + 2j).snapshot()

    # tuples are always converted to lists...can this be fixed?
    # assert_that((1, 2, 3)).snapshot()
    # assert_that({'a': (1,2), 'b': (3,4), 'c': (5,6)}).snapshot()

    assert_that({"custom": "id"}).snapshot(id="mycustomid")

    assert_that({"custom": "path"}).snapshot(path="mycustompath")

    foo = Foo()
    foo2 = Foo(
        {
            "a": 1,
            "b": [1, 2, 3],
            "c": {"x": 1, "y": 2, "z": 3},
            "d": {-1, 2, -3},
            "e": datetime.datetime(2000, 11, 22, 3, 44, 55),
            "f": -1 - 2j,
        }
    )
    bar = Bar()

    assert_that(foo.x).is_equal_to(0)
    assert_that(foo.y).is_equal_to(1)

    assert_that(foo2.x["a"]).is_equal_to(1)
    assert_that(foo2.x["b"]).is_equal_to([1, 2, 3])
    assert_that(foo2.y).is_equal_to(1)

    assert_that(bar.x).is_equal_to(0)
    assert_that(bar.y).is_equal_to(1)

    assert_that(foo).snapshot()
    assert_that(foo2).snapshot()

    try:
        assert_that(bar).snapshot()
        if count == 2:
            fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).contains("Expected ").contains(" to be equal to ").contains("test_snapshots.Bar").contains(
            ", but was not."
        )

    assert_that(
        {
            "none": None,
            "truthy": True,
            "falsy": False,
            "int": 123,
            "intneg": -456,
            "float": 123.456,
            "floatneg": -987.654,
            "empty": "",
            "str": "foo",
            "list": [1, 2, 3],
            "liststr": ["a", "b", "c"],
            "listmix": [1, "a", [2, 4, 6], {1, 2, 3}, 3 + 6j],
            "set": {1, 2, 3},
            "dict": {"a": 1, "b": 2, "c": 3},
            "time": datetime.datetime(2000, 11, 22, 3, 44, 55),
            "complex": 1 + 2j,
            "foo": foo,
            "foo2": foo2,
        }
    ).snapshot()

    assert_that({"__type__": "foo", "__data__": "bar"}).snapshot()


class TestSnapshotCreatedWarning:
    def test_first_capture_warns_and_second_run_compares(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning, match="captured the value instead of comparing"):
            assert_that({"a": 1}).snapshot(id="warn-first", path=str(tmp_path))
        # the suite runs with warnings-as-errors, so a silent pass here proves no second warning
        assert_that({"a": 1}).snapshot(id="warn-first", path=str(tmp_path))

    def test_new_line_in_existing_file_warns(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(1).snapshot(path=str(tmp_path))
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(2).snapshot(path=str(tmp_path))  # same file, new line -> a fresh sub-snap capture

    def test_same_line_second_iteration_compares(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            for value in [7, 7]:
                assert_that(value).snapshot(path=str(tmp_path))

    def test_same_line_second_iteration_fails_on_drift(self, tmp_path):
        values = iter([7, 8])
        with pytest.warns(SnapshotCreatedWarning), pytest.raises(AssertionError):
            for _ in range(2):
                assert_that(next(values)).snapshot(path=str(tmp_path))


class TestSnapshotDatetimeMicroseconds:
    def test_microseconds_survive_the_roundtrip(self, tmp_path):
        timestamp = datetime.datetime(2026, 1, 1, 12, 0, 0, 123456)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(timestamp).snapshot(id="micro", path=str(tmp_path))
        assert_that(timestamp).snapshot(id="micro", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(timestamp.replace(microsecond=999999)).snapshot(id="micro", path=str(tmp_path))

    def test_zero_microseconds_keep_the_historical_format(self, tmp_path):
        # snapshots without sub-second precision must stay readable by older library versions
        timestamp = datetime.datetime(2000, 11, 22, 3, 44, 55)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(timestamp).snapshot(id="legacy", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-legacy.json").read_text())
        assert_that(raw["__data__"]).is_equal_to("2000-11-22 03:44:55")
        assert_that(timestamp).snapshot(id="legacy", path=str(tmp_path))


class TestSnapshotCompareOptions:
    def test_ignore_volatile_field(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"name": "Alice", "ts": 1}).snapshot(id="opt-ignore", path=str(tmp_path))
        assert_that({"name": "Alice", "ts": 999}).snapshot(id="opt-ignore", path=str(tmp_path), ignore="ts")
        with pytest.raises(AssertionError):
            assert_that({"name": "Bob", "ts": 999}).snapshot(id="opt-ignore", path=str(tmp_path), ignore="ts")

    def test_first_capture_stores_full_value_despite_ignore(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"name": "Alice", "ts": 1}).snapshot(id="opt-full", path=str(tmp_path), ignore="ts")
        assert_that({"name": "Alice", "ts": 42}).snapshot(id="opt-full", path=str(tmp_path), ignore="ts")
        with pytest.raises(AssertionError):
            # without ignore the stored ts must be compared, proving the capture kept the full value
            assert_that({"name": "Alice", "ts": 42}).snapshot(id="opt-full", path=str(tmp_path))

    def test_include_only_selected_keys(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1, "b": 2}).snapshot(id="opt-include", path=str(tmp_path))
        assert_that({"a": 1, "b": 999}).snapshot(id="opt-include", path=str(tmp_path), include="a")

    def test_nested_ignore_path(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"user": {"name": "Alice", "session": "s1"}}).snapshot(id="opt-nested", path=str(tmp_path))
        assert_that({"user": {"name": "Alice", "session": "s2"}}).snapshot(
            id="opt-nested", path=str(tmp_path), ignore=[("user", "session")]
        )

    def test_tolerance_absorbs_float_noise(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"price": 1.0}).snapshot(id="opt-tol", path=str(tmp_path))
        assert_that({"price": 1.0004}).snapshot(id="opt-tol", path=str(tmp_path), tolerance=0.001)
        with pytest.raises(AssertionError):
            assert_that({"price": 1.01}).snapshot(id="opt-tol", path=str(tmp_path), tolerance=0.001)

    def test_comparators_own_matching_fields(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"name": "Alice"}).snapshot(id="opt-cmp", path=str(tmp_path))
        assert_that({"name": "ALICE"}).snapshot(
            id="opt-cmp", path=str(tmp_path), comparators={"name": lambda a, e: a.lower() == e.lower()}
        )

    def test_bad_tolerance_fails_on_first_capture(self, tmp_path):
        with pytest.raises(TypeError, match="tolerance arg must be a real number"):
            assert_that({"a": 1}).snapshot(id="opt-bad-tol", path=str(tmp_path), tolerance="high")
        assert_that(os.path.isfile(os.path.join(str(tmp_path), "snap-opt-bad-tol.json"))).is_false()


def test_snapshot_not_serializable(tmp_path):
    with pytest.raises(TypeError) as exc_info:
        assert_that(range(5)).snapshot(id="nonser", path=str(tmp_path))
    assert_that(str(exc_info.value)).ends_with("is not JSON serializable")


def test_snapshot_custom_id_int():
    with pytest.raises(ValueError) as exc_info:
        assert_that("foo").snapshot(id=123)
    assert_that(str(exc_info.value)).starts_with("failed to create snapshot filename")


def test_snapshot_custom_path_none():
    with pytest.raises(ValueError) as exc_info:
        assert_that("foo").snapshot(path=None)
    assert_that(str(exc_info.value)).starts_with("failed to create snapshot filename")


def test_snapshot_does_not_import_arbitrary_modules(tmp_path):
    snap_dir = tmp_path / "__snapshots"
    snap_dir.mkdir()
    snap_file = snap_dir / "snap-cve156.json"
    snap_file.write_text(
        json.dumps(
            {
                "__type__": "instance",
                "__class__": "Exploit",
                "__module__": "cve156_fake_module",
                "__data__": {"pwned": True},
            }
        )
    )

    assert_that(sys.modules).does_not_contain("cve156_fake_module")

    with contextlib.suppress(AssertionError):
        assert_that({"safe": True}).snapshot(id="cve156", path=str(snap_dir))

    assert_that(sys.modules).does_not_contain("cve156_fake_module")


def test_snapshot_returns_dict_for_unknown_module(tmp_path):
    snap_dir = tmp_path / "__snapshots"
    snap_dir.mkdir()
    payload = {
        "__type__": "instance",
        "__class__": "Nope",
        "__module__": "nonexistent_module_xyz",
        "__data__": {"x": 1},
    }
    snap_file = snap_dir / "snap-fallback.json"
    snap_file.write_text(json.dumps(payload))

    with contextlib.suppress(AssertionError):
        assert_that(payload).snapshot(id="fallback", path=str(snap_dir))

    assert_that(sys.modules).does_not_contain("nonexistent_module_xyz")


def test_snapshot_returns_dict_for_missing_class(tmp_path):
    snap_dir = tmp_path / "__snapshots"
    snap_dir.mkdir()
    payload = {
        "__type__": "instance",
        "__class__": "ClassThatDoesNotExist",
        "__module__": "os",
        "__data__": {},
    }
    snap_file = snap_dir / "snap-noclass.json"
    snap_file.write_text(json.dumps(payload))

    with contextlib.suppress(AssertionError):
        assert_that(payload).snapshot(id="noclass", path=str(snap_dir))


class Foo:
    def __init__(self, x=0):
        self.x = x
        self.y = 1

    def __eq__(self, other):
        if isinstance(self, other.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented


class Bar(Foo):
    def __eq__(self, other):
        return NotImplemented


def test_file_lock_times_out_when_held(tmp_path):
    target = str(tmp_path / "data")
    with _file_lock(target), pytest.raises(TimeoutError), _file_lock(target, timeout=0.1, poll=0.02):
        pass


def test_file_lock_serializes_concurrent_writes(tmp_path):
    target = str(tmp_path / "shared.json")
    with open(target, "w") as fp:
        json.dump({}, fp)

    def worker(index):
        with _file_lock(target):
            with open(target) as fp:
                data = json.load(fp)
            data[str(index)] = index
            time.sleep(0.005)  # widen the read-modify-write window to force contention
            with open(target, "w") as fp:
                json.dump(data, fp)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(15)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with open(target) as fp:
        final = json.load(fp)
    assert_that(final).is_length(15)  # every writer's entry survived - no lost updates
