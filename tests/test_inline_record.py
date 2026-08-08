"""Stage-1 recording tests. Run in-process (so coverage counts) without ever applying a rewrite to
this file: `_inline._RECORDS` is monkeypatched to an isolated list, and `apply` is exercised only on
temp files. The full end-to-end rewrite under real pytest is proven by the scratch prototype.
"""

import datetime
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("executing", reason="executing not installed")
pytest.importorskip("asttokens", reason="asttokens not installed")

import assertpy2._inline as _inline
import assertpy2.pytest_plugin as _plugin
import assertpy2.snapshot as _snap
from assertpy2 import assert_that


def _controller_config():
    option = SimpleNamespace(keyword="", markexpr="", last_failed=False, failed_first=False)
    return SimpleNamespace(option=option, pluginmanager=SimpleNamespace(get_plugin=lambda name: None))


class TestRecord:
    def test_records_scalar_and_container(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that({"a": 1, "b": [2, 3]}).matches_inline()
        assert_that(_inline._RECORDS).is_length(1)
        assert_that(_inline._RECORDS[0][3]).is_equal_to("{'a': 1, 'b': [2, 3]}")

    def test_wide_value_is_wrapped_multiline(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        wide = {"user": {"id": 1, "name": "Alice", "roles": ["admin", "editor", "viewer"]}, "meta": {"total": 3}}
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that(wide).matches_inline()
        assert_that(_inline._RECORDS[0][3]).contains("\n")

    def test_non_literalable_is_rejected(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        with pytest.raises(TypeError, match="use snapshot"):
            assert_that(datetime.datetime(2020, 1, 1)).matches_inline()
        assert_that(_inline._RECORDS).is_empty()


class TestApply:
    def test_apply_inserts_at_offset(self, tmp_path, monkeypatch):
        target = tmp_path / "snap_me.py"
        target.write_text("at().matches_inline()\n", encoding="utf-8")
        monkeypatch.setattr(_inline, "_RECORDS", [(str(target), 20, 20, "{'a': 1}")])
        touched = _inline.apply_inline_records()
        assert_that(touched).contains(str(target))
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline({'a': 1})\n")

    def test_apply_replaces_range(self, tmp_path, monkeypatch):
        target = tmp_path / "snap_upd.py"
        target.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(_inline, "_RECORDS", [(str(target), 4, 5, "2")])
        _inline.apply_inline_records()
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("x = 2\n")


class TestUpdate:
    def test_drift_under_update_records_replacement(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that({"a": 2}).matches_inline({"a": 1})
        assert_that(_inline._RECORDS).is_length(1)
        assert_that(_inline._RECORDS[0][3]).is_equal_to("{'a': 2}")

    def test_no_drift_under_update_is_noop(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        assert_that({"a": 1}).matches_inline({"a": 1})
        assert_that(_inline._RECORDS).is_empty()

    def test_update_non_literalable_rejected(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        with pytest.raises(TypeError, match="use snapshot"):
            assert_that(datetime.datetime(2020, 1, 1)).matches_inline(datetime.datetime(2019, 1, 1))


class TestXdist:
    def test_worker_ships_inline_records(self, monkeypatch):
        monkeypatch.setattr(_inline, "_RECORDS", [("/x/test_a.py", 5, 5, "{'a': 1}")])
        config = SimpleNamespace(workeroutput={})
        _plugin.pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy2_inline"]).is_equal_to([["/x/test_a.py", 5, 5, "{'a': 1}"]])

    def test_controller_collects_worker_inline(self):
        _plugin._controller_inline.clear()
        node = SimpleNamespace(workeroutput={"assertpy2_inline": [["/x/test_a.py", 5, 5, "{'a': 1}"]]})
        _plugin.pytest_testnodedown(node, None)
        assert_that(_plugin._controller_inline).contains(("/x/test_a.py", 5, 5, "{'a': 1}"))
        _plugin._controller_inline.clear()

    def test_controller_applies_collected_inline(self, tmp_path, monkeypatch):
        target = tmp_path / "shipped.py"
        target.write_text("at().matches_inline()\n", encoding="utf-8")
        monkeypatch.setattr(_inline, "_RECORDS", [])
        monkeypatch.setattr(_snap, "_TOUCHED", set())
        _plugin._controller_touched.clear()
        _plugin._controller_inline.clear()
        _plugin._controller_inline.append((str(target), 20, 20, "{'a': 1}"))
        _plugin.pytest_sessionfinish(SimpleNamespace(config=_controller_config()), 0)
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline({'a': 1})\n")
        assert_that(_plugin._controller_inline).is_empty()


class TestGuards:
    def test_is_literalable(self):
        assert_that(_inline.is_literalable({"a": [1, 2], "b": (3, None)})).is_true()
        assert_that(_inline.is_literalable({"a": datetime.date(2020, 1, 1)})).is_false()
        assert_that(_inline.is_literalable([1, object()])).is_false()

    def test_missing_tooling(self):
        with patch.dict(sys.modules, {"executing": None}), pytest.raises(ImportError, match=r"assertpy2\[inline\]"):
            _inline._ensure_inline_tooling()


class TestRecordedPosition:
    """Where the rewrite lands, and at what indentation.  The tests above assert the recorded *text*
    and never the offsets, so an off-by-one in either would rewrite the wrong characters and still
    pass every one of them.  Each check reads this file back and compares against what the source
    actually says, rather than restating the implementation's arithmetic.
    """

    @staticmethod
    def _source_of(filename):
        return pathlib.Path(filename).read_text(encoding="utf-8")

    def test_a_create_inserts_just_inside_the_closing_paren(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that(1).matches_inline()
        filename, start, end, _text = _inline._RECORDS[0]
        source = self._source_of(filename)
        assert_that(start).is_equal_to(end)  # an insertion, so the range is empty
        assert_that(source[start]).is_equal_to(")")
        assert_that(source[start - len("matches_inline(") : start]).is_equal_to("matches_inline(")

    def test_an_update_replaces_exactly_the_old_literal(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that({"a": 2}).matches_inline({"a": 1})
        filename, start, end, _text = _inline._RECORDS[0]
        assert_that(self._source_of(filename)[start:end]).is_equal_to('{"a": 1}')

    def test_a_created_multiline_literal_is_indented_to_the_call(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        wide = {"user": {"id": 1, "name": "Alice", "roles": ["admin", "editor", "viewer"]}, "meta": {"total": 3}}
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that(wide).matches_inline()
        filename, start, _end, text = _inline._RECORDS[0]
        source = self._source_of(filename)
        column = start - (source.rfind("\n", 0, start) + 1)  # characters between the line start and here
        assert_that(text).contains("\n")
        # the column is read off this file, so an off-by-one in the recorder's own arithmetic surfaces
        # as a different rendering here; `_format_literal` itself is pinned by TestFormatLiteral
        assert_that(text).is_equal_to(_inline._format_literal(wide, column))

    def test_an_updated_multiline_literal_is_indented_to_the_literal(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_RECORDS", [])
        wide = {"user": {"id": 2, "name": "Alice", "roles": ["admin", "editor", "viewer"]}, "meta": {"total": 3}}
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that(wide).matches_inline({"user": 1})
        filename, start, _end, text = _inline._RECORDS[0]
        source = self._source_of(filename)
        column = start - (source.rfind("\n", 0, start) + 1)
        assert_that(text).contains("\n")
        assert_that(text).is_equal_to(_inline._format_literal(wide, column))
