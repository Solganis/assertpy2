import collections
import contextlib
import datetime
import decimal
import enum
import json
import os
import shutil
import sys
import threading
import time
import uuid

import pytest

from assertpy2 import (
    SnapshotCreatedWarning,
    SnapshotUpdatedWarning,
    assert_that,
    fail,
    match,
    register_snapshot_serializer,
    soft_assertions,
)
from assertpy2 import snapshot as _snapshot
from assertpy2.snapshot import _ci_mode_enabled, _file_lock, _load


class Color(enum.Enum):
    RED = 1
    GREEN = 2


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


class TestSnapshotTypedCodec:
    def test_date_roundtrip(self, tmp_path):
        value = datetime.date(2026, 7, 4)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-date", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-date", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(datetime.date(2026, 7, 5)).snapshot(id="codec-date", path=str(tmp_path))

    def test_date_stored_as_iso_marker(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(datetime.date(2026, 7, 4)).snapshot(id="codec-date-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-codec-date-raw.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "date", "__data__": "2026-07-04"})

    def test_non_string_key_dict_roundtrip(self, tmp_path):
        # json coerces non-string keys to strings; the codec must round-trip int/None/tuple keys intact
        value = {1: "a", 2: "b", None: "c", (3, 4): "d"}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-intkeys", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-intkeys", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that({1: "a", 2: "CHANGED"}).snapshot(id="codec-intkeys", path=str(tmp_path))

    def test_marker_key_dict_is_not_mistaken_for_an_envelope(self, tmp_path):
        # a user dict that happens to carry the codec's marker keys must round-trip as a plain dict
        value = {"__type__": "date", "__data__": "not-a-date"}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-collide", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-collide", path=str(tmp_path))

    def test_normal_string_dict_stored_without_envelope(self, tmp_path):
        # a plain string-keyed dict must stay an ordinary JSON object (no envelope), so existing
        # snapshots remain byte-identical
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1, "b": 2}).snapshot(id="codec-plain", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-codec-plain.json").read_text())
        assert_that(raw).is_equal_to({"a": 1, "b": 2})

    def test_unknown_type_marker_decodes_as_is(self, tmp_path):
        # a snapshot written by a future version with an unknown type marker must decode to the raw
        # dict (forward-compatible), not error
        snap = tmp_path / "snap-future.json"
        snap.write_text(json.dumps({"__type__": "future_type", "__data__": [1, 2]}))
        assert_that(_load(str(snap))).is_equal_to({"__type__": "future_type", "__data__": [1, 2]})

    def test_time_roundtrip(self, tmp_path):
        value = datetime.time(12, 34, 56, 789012)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-time", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-time", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(datetime.time(12, 34, 57)).snapshot(id="codec-time", path=str(tmp_path))

    def test_time_with_utc_offset_roundtrip(self, tmp_path):
        value = datetime.time(12, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-time-tz", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-time-tz", path=str(tmp_path))

    def test_decimal_roundtrip(self, tmp_path):
        value = decimal.Decimal("1.10")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-decimal", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-decimal", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(decimal.Decimal("1.2")).snapshot(id="codec-decimal", path=str(tmp_path))

    def test_decimal_stored_as_exact_string(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(decimal.Decimal("1.10")).snapshot(id="codec-decimal-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-codec-decimal-raw.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "decimal", "__data__": "1.10"})

    def test_bytes_roundtrip(self, tmp_path):
        value = b"\x00\xffbinary"
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-bytes", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-bytes", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(b"other").snapshot(id="codec-bytes", path=str(tmp_path))

    def test_bytes_stored_base64(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(b"\x00\xff").snapshot(id="codec-bytes-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-codec-bytes-raw.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "bytes", "__data__": "AP8="})

    def test_bytearray_compares_against_stored_bytes(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(bytearray(b"ab")).snapshot(id="codec-bytearray", path=str(tmp_path))
        assert_that(bytearray(b"ab")).snapshot(id="codec-bytearray", path=str(tmp_path))
        assert_that(b"ab").snapshot(id="codec-bytearray", path=str(tmp_path))

    def test_aware_datetime_roundtrip(self, tmp_path):
        # tz-aware datetimes previously lost their offset on save and never compared equal again
        zone = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        value = datetime.datetime(2026, 7, 4, 10, 0, 0, tzinfo=zone)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-aware", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-aware", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(value + datetime.timedelta(hours=1)).snapshot(id="codec-aware", path=str(tmp_path))

    def test_aware_datetime_with_microseconds_roundtrip(self, tmp_path):
        value = datetime.datetime(2026, 7, 4, 10, 0, 0, 123456, tzinfo=datetime.timezone.utc)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-aware-micro", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-aware-micro", path=str(tmp_path))

    def test_negative_offset_datetime_roundtrip(self, tmp_path):
        zone = datetime.timezone(datetime.timedelta(hours=-5))
        value = datetime.datetime(2026, 7, 4, 10, 0, 0, tzinfo=zone)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-aware-neg", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-aware-neg", path=str(tmp_path))

    def test_subminute_offset_datetime_roundtrip(self, tmp_path):
        # legal since 3.7; strftime renders "+000530" and strptime %z parses it back
        zone = datetime.timezone(datetime.timedelta(minutes=5, seconds=30))
        value = datetime.datetime(2026, 7, 4, 10, 0, 0, tzinfo=zone)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-aware-subminute", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-aware-subminute", path=str(tmp_path))

    def test_nested_typed_values_roundtrip(self, tmp_path):
        value = {
            "day": datetime.date(2026, 7, 4),
            "at": datetime.time(9, 30),
            "price": decimal.Decimal("19.99"),
            "blob": b"\x01\x02",
        }
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-nested", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-nested", path=str(tmp_path))


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


class TestSnapshotUpdateMode:
    def test_stale_snapshot_updated_and_warns(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="upd", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning, match="overwrote the stored value"):
            assert_that({"a": 2}).snapshot(id="upd", path=str(tmp_path))
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_UPDATE")
        assert_that({"a": 2}).snapshot(id="upd", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that({"a": 1}).snapshot(id="upd", path=str(tmp_path))

    def test_matching_snapshot_is_not_rewritten(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="upd-same", path=str(tmp_path))
        target = tmp_path / "snap-upd-same.json"
        stamp = os.stat(target).st_mtime_ns
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        # the suite runs warnings-as-errors, so a silent pass here also proves no update warning
        assert_that({"a": 1}).snapshot(id="upd-same", path=str(tmp_path))
        assert_that(os.stat(target).st_mtime_ns).is_equal_to(stamp)

    def test_first_capture_in_update_mode_warns_created(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="upd-first", path=str(tmp_path))

    def test_lineno_subsnap_updates(self, tmp_path, monkeypatch):
        def snap(value):
            return assert_that(value).snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            snap(7)
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning):
            snap(8)
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_UPDATE")
        snap(8)
        with pytest.raises(AssertionError):
            snap(7)

    def test_update_preserves_sibling_subsnaps(self, tmp_path, monkeypatch):
        def snap_a(value):
            return assert_that(value).snapshot(path=str(tmp_path))

        def snap_b(value):
            return assert_that(value).snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            snap_a(1)
        with pytest.warns(SnapshotCreatedWarning):
            snap_b("keep")
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning):
            snap_a(2)
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_UPDATE")
        snap_a(2)
        snap_b("keep")

    def test_update_honors_ignore_option(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"name": "Alice", "ts": 1}).snapshot(id="upd-ign", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        # drift only in the ignored field counts as matching, so nothing is rewritten
        assert_that({"name": "Alice", "ts": 999}).snapshot(id="upd-ign", path=str(tmp_path), ignore="ts")
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_UPDATE")
        with pytest.raises(AssertionError):
            # the stored ts must still be the original 1
            assert_that({"name": "Alice", "ts": 999}).snapshot(id="upd-ign", path=str(tmp_path))

    def test_disabled_env_value_keeps_normal_failure(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(1).snapshot(id="upd-off", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "0")
        with pytest.raises(AssertionError):
            assert_that(2).snapshot(id="upd-off", path=str(tmp_path))

    def test_update_inside_soft_assertions_collects_nothing(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(1).snapshot(id="upd-soft", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning), soft_assertions():
            assert_that(2).snapshot(id="upd-soft", path=str(tmp_path))
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_UPDATE")
        assert_that(2).snapshot(id="upd-soft", path=str(tmp_path))


class TestSnapshotBuiltinCodecExtras:
    def test_uuid_roundtrip(self, tmp_path):
        value = uuid.uuid4()
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="uuid", path=str(tmp_path))
        assert_that(value).snapshot(id="uuid", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(uuid.uuid4()).snapshot(id="uuid", path=str(tmp_path))

    def test_uuid_stored_as_string(self, tmp_path):
        value = uuid.UUID("12345678-1234-5678-1234-567812345678")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="uuid-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-uuid-raw.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "uuid", "__data__": "12345678-1234-5678-1234-567812345678"})

    def test_enum_roundtrip(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(Color.RED).snapshot(id="enum", path=str(tmp_path))
        assert_that(Color.RED).snapshot(id="enum", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(Color.GREEN).snapshot(id="enum", path=str(tmp_path))

    def test_enum_stored_by_value_and_class(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(Color.RED).snapshot(id="enum-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-enum-raw.json").read_text())
        assert_that(raw["__type__"]).is_equal_to("enum")
        assert_that(raw["__data__"]).is_equal_to(1)
        assert_that(raw["__class__"]).is_equal_to("Color")

    def test_enum_unresolvable_module_returns_dict(self, tmp_path):
        payload = {"__type__": "enum", "__class__": "Nope", "__module__": "nonexistent_mod_xyz", "__data__": 1}
        snap_file = tmp_path / "snap-e.json"
        snap_file.write_text(json.dumps(payload))
        assert_that(_load(str(snap_file))).is_equal_to(payload)

    def test_enum_missing_class_returns_dict(self, tmp_path):
        payload = {"__type__": "enum", "__class__": "DoesNotExist", "__module__": "os", "__data__": 1}
        snap_file = tmp_path / "snap-e2.json"
        snap_file.write_text(json.dumps(payload))
        assert_that(_load(str(snap_file))).is_equal_to(payload)


class TestSnapshotSerializerRegistry:
    def test_custom_type_roundtrip(self, tmp_path):
        register_snapshot_serializer(_Money, lambda m: m.cents, lambda c: _Money(c), tag="money")
        value = {"price": _Money(500)}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="ser-money", path=str(tmp_path))
        assert_that(value).snapshot(id="ser-money", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that({"price": _Money(999)}).snapshot(id="ser-money", path=str(tmp_path))

    def test_stored_with_custom_marker_and_tag(self, tmp_path):
        register_snapshot_serializer(_Money, lambda m: m.cents, lambda c: _Money(c), tag="money")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(_Money(7)).snapshot(id="ser-tag", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-ser-tag.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "custom", "__tag__": "money", "__data__": 7})

    def test_default_tag_is_qualified_name(self):
        register_snapshot_serializer(_Money, lambda m: m.cents, lambda c: _Money(c))
        assert_that(_snapshot._SERIALIZERS[0].tag).ends_with("._Money")

    def test_isinstance_matches_subclasses(self, tmp_path):
        register_snapshot_serializer(_Money, lambda m: m.cents, lambda c: _Money(c), tag="money")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(_Cents(3)).snapshot(id="ser-sub", path=str(tmp_path))  # subclass matches by isinstance
        raw = json.loads((tmp_path / "snap-ser-sub.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "custom", "__tag__": "money", "__data__": 3})

    def test_last_registered_wins(self, tmp_path):
        register_snapshot_serializer(_Money, lambda m: "first", lambda d: _Money(0), tag="t1")
        register_snapshot_serializer(_Money, lambda m: "second", lambda d: _Money(0), tag="t2")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(_Money(0)).snapshot(id="ser-last", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-ser-last.json").read_text())
        assert_that(raw["__tag__"]).is_equal_to("t2")

    def test_unknown_custom_tag_returns_marker(self, tmp_path):
        payload = {"__type__": "custom", "__tag__": "not-registered", "__data__": 5}
        snap_file = tmp_path / "snap-unk.json"
        snap_file.write_text(json.dumps(payload))
        assert_that(_load(str(snap_file))).is_equal_to(payload)

    def test_encode_skips_non_matching_serializer(self, tmp_path):
        register_snapshot_serializer(_Money, lambda m: m.cents, lambda c: _Money(c), tag="money")
        # a set is not a _Money: the registry is checked, skipped, then the built-in set codec handles it
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({1, 2, 3}).snapshot(id="ser-skip", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-ser-skip.json").read_text())
        assert_that(raw["__type__"]).is_equal_to("set")

    def test_decode_skips_non_matching_tag(self, tmp_path):
        register_snapshot_serializer(_Money, lambda m: m.cents, lambda c: _Money(c), tag="money")
        payload = {"__type__": "custom", "__tag__": "other-tag", "__data__": 5}
        snap_file = tmp_path / "snap-tagskip.json"
        snap_file.write_text(json.dumps(payload))
        assert_that(_load(str(snap_file))).is_equal_to(payload)  # tag mismatch -> loop skips -> marker returned

    def test_register_rejects_non_type(self):
        with pytest.raises(TypeError, match="cls must be a type"):
            register_snapshot_serializer("not a type", str, str)

    def test_register_rejects_non_callable_encode(self):
        with pytest.raises(TypeError, match="must be callable"):
            register_snapshot_serializer(int, "nope", str)

    def test_register_rejects_non_callable_decode(self):
        with pytest.raises(TypeError, match="must be callable"):
            register_snapshot_serializer(int, str, "nope")


class _Money:
    def __init__(self, cents):
        self.cents = cents

    def __eq__(self, other):
        return isinstance(other, _Money) and other.cents == self.cents


class _Cents(_Money):
    pass


_UUID_A = "550e8400-e29b-41d4-a716-446655440000"
_UUID_B = "11111111-2222-3333-4444-555555555555"


class TestSnapshotOrphanDetection:
    def _write(self, tmp_path, name, data):
        snap_file = tmp_path / f"snap-{name}.json"
        snap_file.write_text(json.dumps(data))
        return str(snap_file)

    def test_sub_key_orphan_in_touched_file(self, tmp_path):
        snapname = self._write(tmp_path, "mod", {"10": 1, "20": 2, "30": 3})
        sub, whole = _snapshot._find_orphans({(snapname, "10"), (snapname, "20")})  # 30 not exercised
        assert_that(sub).is_equal_to([(snapname, "30")])
        assert_that(whole).is_empty()

    def test_whole_file_orphan_untouched(self, tmp_path):
        live = self._write(tmp_path, "live", {"10": 1})
        dead = self._write(tmp_path, "dead", {"10": 1})
        sub, whole = _snapshot._find_orphans({(live, "10")})
        assert_that(whole).is_equal_to([dead])
        assert_that(sub).is_empty()

    def test_custom_id_touched_not_orphan(self, tmp_path):
        snapname = self._write(tmp_path, "custom", {"any": "value"})
        sub, whole = _snapshot._find_orphans({(snapname, "")})  # touched as a whole-file custom id
        assert_that(sub).is_empty()
        assert_that(whole).is_empty()

    def test_missing_directory_skipped(self, tmp_path):
        snapname = str(tmp_path / "gone" / "snap-x.json")
        sub, whole = _snapshot._find_orphans({(snapname, "10")})
        assert_that(sub).is_empty()
        assert_that(whole).is_empty()

    def test_non_snapshot_files_ignored(self, tmp_path):
        snapname = self._write(tmp_path, "mod", {"10": 1})
        (tmp_path / "readme.txt").write_text("x")
        sub, whole = _snapshot._find_orphans({(snapname, "10")})
        assert_that(sub).is_empty()
        assert_that(whole).is_empty()

    def test_prune_removes_key_keeping_others(self, tmp_path):
        keep = self._write(tmp_path, "keep", {"10": 1, "30": 3})
        _snapshot._prune_sub_key_orphans([(keep, "30")])
        assert_that(json.loads((tmp_path / "snap-keep.json").read_text())).is_equal_to({"10": 1})

    def test_prune_deletes_emptied_file(self, tmp_path):
        empty = self._write(tmp_path, "empty", {"10": 1})
        _snapshot._prune_sub_key_orphans([(empty, "10")])
        assert_that(os.path.isfile(empty)).is_false()


class TestSnapshotPlaceholders:
    def test_capture_stores_token_not_value(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "name": "Alice"}).snapshot(
                id="ph", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        raw = json.loads((tmp_path / "snap-ph.json").read_text())
        assert_that(raw).is_equal_to({"id": {"__placeholder__": "a valid UUID string"}, "name": "Alice"})

    def test_different_volatile_value_passes(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "name": "Alice"}).snapshot(
                id="ph2", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        assert_that({"id": _UUID_B, "name": "Alice"}).snapshot(
            id="ph2", path=str(tmp_path), placeholders={"id": match.is_uuid()}
        )

    def test_non_matching_placeholder_fails(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A}).snapshot(id="ph3", path=str(tmp_path), placeholders={"id": match.is_uuid()})
        with pytest.raises(AssertionError, match=r"placeholder <id> to satisfy a valid UUID string"):
            assert_that({"id": "not-a-uuid"}).snapshot(
                id="ph3", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )

    def test_missing_placeholder_key_fails(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A}).snapshot(id="ph4", path=str(tmp_path), placeholders={"id": match.is_uuid()})
        with pytest.raises(AssertionError, match="but was missing"):
            assert_that({"other": 1}).snapshot(id="ph4", path=str(tmp_path), placeholders={"id": match.is_uuid()})

    def test_drift_in_non_placeholder_field_still_caught(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "name": "Alice"}).snapshot(
                id="ph5", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        with pytest.raises(AssertionError):
            assert_that({"id": _UUID_B, "name": "Bob"}).snapshot(
                id="ph5", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )

    def test_callable_placeholder(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"n": 5}).snapshot(id="ph6", path=str(tmp_path), placeholders={"n": lambda v: v > 0})
        assert_that({"n": 99}).snapshot(id="ph6", path=str(tmp_path), placeholders={"n": lambda v: v > 0})
        with pytest.raises(AssertionError):
            assert_that({"n": -1}).snapshot(id="ph6", path=str(tmp_path), placeholders={"n": lambda v: v > 0})

    def test_combines_with_list_ignore(self, tmp_path):
        placeholders = {"id": match.is_uuid()}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "other": 1, "keep": "x"}).snapshot(
                id="ph7", path=str(tmp_path), placeholders=placeholders, ignore=["other"]
            )
        assert_that({"id": _UUID_B, "other": 999, "keep": "x"}).snapshot(
            id="ph7", path=str(tmp_path), placeholders=placeholders, ignore=["other"]
        )

    def test_combines_with_single_key_ignore(self, tmp_path):
        placeholders = {"id": match.is_uuid()}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "other": 1, "keep": "x"}).snapshot(
                id="ph8", path=str(tmp_path), placeholders=placeholders, ignore="other"
            )
        assert_that({"id": _UUID_B, "other": 999, "keep": "x"}).snapshot(
            id="ph8", path=str(tmp_path), placeholders=placeholders, ignore="other"
        )

    def test_failure_collected_under_soft(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A}).snapshot(id="ph9", path=str(tmp_path), placeholders={"id": match.is_uuid()})
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_that({"id": "bad"}).snapshot(id="ph9", path=str(tmp_path), placeholders={"id": match.is_uuid()})

    def test_update_mode_rewrites_keeping_token(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "v": 1}).snapshot(
                id="ph10", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning):
            assert_that({"id": _UUID_B, "v": 2}).snapshot(
                id="ph10", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        raw = json.loads((tmp_path / "snap-ph10.json").read_text())
        assert_that(raw["v"]).is_equal_to(2)
        assert_that(raw["id"]).is_equal_to({"__placeholder__": "a valid UUID string"})

    def test_non_dict_val_raises(self, tmp_path):
        with pytest.raises(TypeError):
            assert_that([1, 2, 3]).snapshot(id="ph11", path=str(tmp_path), placeholders={"id": match.is_uuid()})

    def test_non_matcher_value_raises(self, tmp_path):
        with pytest.raises(TypeError, match="Matcher instances or callables"):
            assert_that({"id": _UUID_A}).snapshot(id="ph12", path=str(tmp_path), placeholders={"id": "not a matcher"})


class TestSnapshotCiMode:
    def test_ci_mode_enabled_precedence(self, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        assert_that(_ci_mode_enabled()).is_true()
        monkeypatch.setattr(_snapshot, "_CI_MODE", False)
        assert_that(_ci_mode_enabled()).is_false()
        # flag unset -> explicit env wins, off/on both honored
        monkeypatch.setattr(_snapshot, "_CI_MODE", None)
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_CI", "off")
        assert_that(_ci_mode_enabled()).is_false()
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_CI", "yes")
        assert_that(_ci_mode_enabled()).is_true()
        # no explicit env -> autodetect the CI marker
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_CI")
        monkeypatch.setenv("CI", "1")
        assert_that(_ci_mode_enabled()).is_true()
        monkeypatch.setenv("CI", "")
        assert_that(_ci_mode_enabled()).is_false()

    def test_ci_flag_fails_on_missing_whole_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionError, match="does not exist and CI mode forbids"):
            assert_that({"a": 1}).snapshot(id="ci-missing", path=str(tmp_path))
        assert_that(os.path.isfile(os.path.join(str(tmp_path), "snap-ci-missing.json"))).is_false()

    def test_ci_env_fails_on_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", None)
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_CI", "1")
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that({"a": 1}).snapshot(id="ci-env", path=str(tmp_path))

    def test_ci_autodetect_via_ci_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", None)
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_CI", raising=False)
        monkeypatch.setenv("CI", "true")
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that({"a": 1}).snapshot(id="ci-auto", path=str(tmp_path))

    def test_ci_env_off_beats_autodetect(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", None)
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_CI", "0")
        monkeypatch.setenv("CI", "true")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="ci-off", path=str(tmp_path))
        assert_that(os.path.isfile(os.path.join(str(tmp_path), "snap-ci-off.json"))).is_true()

    def test_ci_existing_snapshot_still_compares(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="ci-exist", path=str(tmp_path))
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        assert_that({"a": 1}).snapshot(id="ci-exist", path=str(tmp_path))  # match -> passes, no create
        with pytest.raises(AssertionError):  # mismatch -> normal compare failure, not the CI one
            assert_that({"a": 2}).snapshot(id="ci-exist", path=str(tmp_path))

    def test_ci_fails_on_missing_lineno_subsnap(self, tmp_path, monkeypatch):
        def snap(value):
            return assert_that(value).snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            snap(1)  # creates the file, keyed by snap()'s line number
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        # a different call site -> different line number -> absent in the existing file -> CI forbids
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that(2).snapshot(path=str(tmp_path))


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


_CONTRACT_SAMPLE = {"id": 1, "total": 5, "created": None, "customer": {"name": "A"}, "items": [{"sku": "X", "qty": 1}]}


class TestContractSnapshot:
    def test_first_run_creates_and_warns(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning, match="captured the shape"):
            assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-first", path=str(tmp_path))

    @pytest.mark.filterwarnings("ignore::assertpy2.snapshot.SnapshotCreatedWarning")
    def test_value_tolerant_same_structure_passes(self, tmp_path):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-tol", path=str(tmp_path))
        changed = {"id": 999, "total": 8.75, "created": "2026-07-06", "customer": {"name": "Z"}, "items": []}
        assert_that(changed).matches_contract_snapshot(id="c-tol", path=str(tmp_path))  # values differ, shape same

    @pytest.mark.filterwarnings("ignore::assertpy2.snapshot.SnapshotCreatedWarning")
    def test_added_field_drift_fails_with_report(self, tmp_path):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-add", path=str(tmp_path))
        grew = {**_CONTRACT_SAMPLE, "promo": "X", "customer": {"name": "A", "vip": True}}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(grew).matches_contract_snapshot(id="c-add", path=str(tmp_path))
        message = str(exc_info.value)
        assert_that(message).contains("structure").contains("+ promo").contains("+ customer.vip")

    @pytest.mark.filterwarnings("ignore::assertpy2.snapshot.SnapshotCreatedWarning")
    def test_removed_and_retyped_drift_fails(self, tmp_path):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-rr", path=str(tmp_path))
        shrank = {k: v for k, v in _CONTRACT_SAMPLE.items() if k != "total"}
        with pytest.raises(AssertionError, match=r"- total"):
            assert_that(shrank).matches_contract_snapshot(id="c-rr", path=str(tmp_path))
        retyped = {**_CONTRACT_SAMPLE, "id": "1"}
        with pytest.raises(AssertionError, match="number -> str"):
            assert_that(retyped).matches_contract_snapshot(id="c-rr", path=str(tmp_path))

    @pytest.mark.filterwarnings("ignore::assertpy2.snapshot.SnapshotCreatedWarning")
    def test_list_element_drift(self, tmp_path):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-list", path=str(tmp_path))
        drifted = {**_CONTRACT_SAMPLE, "items": [{"sku": "X", "qty": 1, "gift": True}]}
        with pytest.raises(AssertionError, match=r"items\[\*\]\.gift"):
            assert_that(drifted).matches_contract_snapshot(id="c-list", path=str(tmp_path))

    def test_lineno_based_create_then_compare(self, tmp_path):
        payloads = iter([{"a": 1}, {"a": 2}])  # same line, second run compares (same shape -> passes)
        with pytest.warns(SnapshotCreatedWarning):
            for _ in range(2):
                assert_that(next(payloads)).matches_contract_snapshot(path=str(tmp_path))

    def test_new_line_in_existing_file_creates(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).matches_contract_snapshot(path=str(tmp_path))
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"b": 2}).matches_contract_snapshot(path=str(tmp_path))  # same file, new sub-snap

    @pytest.mark.filterwarnings("ignore::assertpy2.snapshot.SnapshotCreatedWarning")
    def test_update_mode_rewrites_drifted_id(self, tmp_path, monkeypatch):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-up", path=str(tmp_path))
        grew = {**_CONTRACT_SAMPLE, "promo": "X"}
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning, match="overwrote the stored shape"):
            assert_that(grew).matches_contract_snapshot(id="c-up", path=str(tmp_path))
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_UPDATE")
        assert_that(grew).matches_contract_snapshot(id="c-up", path=str(tmp_path))  # rewritten shape now matches

    def test_update_mode_rewrites_drifted_lineno(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        values = iter([{"a": 1}, {"a": 1, "b": 2}])  # both calls below share one source line
        for expected in (SnapshotCreatedWarning, SnapshotUpdatedWarning):
            with pytest.warns(expected):
                assert_that(next(values)).matches_contract_snapshot(path=str(tmp_path))

    @pytest.mark.filterwarnings("ignore::assertpy2.snapshot.SnapshotCreatedWarning")
    def test_update_mode_leaves_matching_untouched(self, tmp_path, monkeypatch):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-keep", path=str(tmp_path))
        target = os.path.join(str(tmp_path), "snap-c-keep.json")
        before = os.path.getmtime(target)
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(
            id="c-keep", path=str(tmp_path)
        )  # same shape, no rewrite
        assert_that(os.path.getmtime(target)).is_equal_to(before)

    def test_ci_mode_forbids_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-ci", path=str(tmp_path))


class TestMismatchNamesItsSnapshot:
    """A mismatch must say which stored value it measured against, and how to accept the new one."""

    def test_named_snapshot_is_identified(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="named-snap", path=str(tmp_path))
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"a": 99}).snapshot(id="named-snap", path=str(tmp_path))
        message = str(exc_info.value)
        assert_that(message).contains("named-snap")
        assert_that(message).contains("--assertpy2-snapshot-update")

    def test_line_keyed_snapshots_are_told_apart(self, tmp_path):
        # without an id the file holds one entry per line of the calling code, so each call site needs
        # to run twice: once to record, once to compare
        def first(value):
            assert_that(value).snapshot(path=str(tmp_path))

        def second(value):
            assert_that(value).snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            first({"a": 1})
        with pytest.warns(SnapshotCreatedWarning):
            second({"b": 1})
        with pytest.raises(AssertionError) as first_failure:
            first({"a": 99})
        with pytest.raises(AssertionError) as second_failure:
            second({"b": 99})
        assert_that(str(first_failure.value)).contains("::")
        assert_that(str(first_failure.value)).is_not_equal_to(str(second_failure.value))

    def test_the_diff_survives_the_added_identity(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": {"b": 1}}).snapshot(id="diff-snap", path=str(tmp_path))
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"a": {"b": 2}}).snapshot(id="diff-snap", path=str(tmp_path))
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("a.b")


class TestContractSnapshotNamesItself:
    """The drift report says which contract it measured against, like both sibling snapshot kinds."""

    def test_named_contract_is_identified(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": 1, "tags": ["a"]}).matches_contract_snapshot(id="ct-named", path=str(tmp_path))
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"id": "one", "extra": 2}).matches_contract_snapshot(id="ct-named", path=str(tmp_path))
        message = str(exc_info.value)
        assert_that(message).contains("ct-named")
        assert_that(message).contains("--assertpy2-snapshot-update")
        # the purpose-built drift notation stays: the generic diff renderer reads worse here
        assert_that(message).contains("+ extra")
        assert_that(message).contains("~ id number -> str")

    def test_line_keyed_contracts_are_told_apart(self, tmp_path):
        def first(value):
            assert_that(value).matches_contract_snapshot(path=str(tmp_path))

        def second(value):
            assert_that(value).matches_contract_snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            first({"a": 1})
        with pytest.warns(SnapshotCreatedWarning):
            second({"b": 1})
        with pytest.raises(AssertionError) as first_failure:
            first({"a": "one"})
        with pytest.raises(AssertionError) as second_failure:
            second({"b": "one"})
        assert_that(str(first_failure.value)).contains("::")
        assert_that(str(first_failure.value)).is_not_equal_to(str(second_failure.value))


class TestCyclicValues:
    """Every other walker in the library marks a cycle; these two used to recurse until the stack gave out."""

    def test_snapshot_names_the_cycle_instead_of_recursing(self, tmp_path):
        node = {"id": 1}
        node["self"] = node
        with pytest.raises(ValueError, match="circular reference"):
            assert_that(node).snapshot(id="cyc", path=str(tmp_path))

    def test_contract_snapshot_records_a_cycle_marker(self, tmp_path):
        node = {"id": 1}
        node["self"] = node
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(node).matches_contract_snapshot(id="cyc-shape", path=str(tmp_path))
