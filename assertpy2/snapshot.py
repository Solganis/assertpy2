from __future__ import annotations

import contextlib
import datetime
import inspect
import json
import os
import sys
import time
import warnings
from typing import TYPE_CHECKING, Final

from ._compare import _build_compare_config
from ._mixin_base import _MixinBase

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ._compat import Self

__tracebackhide__ = True

_UNSET: Final = object()


class SnapshotCreatedWarning(UserWarning):
    """Emitted when `snapshot()` writes a new snapshot instead of comparing.

    The first run of a snapshot assertion captures the current value and passes without comparing
    anything, so a wrong first capture would silently become the reference.  This warning makes that
    capture visible; suites running with ``-W error`` turn it into an explicit failure.
    """


@contextlib.contextmanager
def _file_lock(target: str, *, timeout: float = 10.0, poll: float = 0.05) -> Iterator[None]:
    """Serialize snapshot read-modify-write across processes via an ``O_EXCL`` lock file.

    Not crash-safe: a process that dies while holding the lock leaves a stale lock file and other
    writers time out.  Accepted for now - snapshots are dev-time artifacts and crashes mid-write are rare.
    """
    lockpath = f"{target}.lock"
    deadline = time.monotonic() + timeout
    lock_fd = None
    while lock_fd is None:
        try:
            lock_fd = os.open(lockpath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:  # noqa: PERF203  # retry the O_EXCL acquire each poll until the lock frees
            if time.monotonic() >= deadline:
                raise TimeoutError(f"could not acquire snapshot lock <{lockpath}> within {timeout}s") from None
            time.sleep(poll)
    try:
        yield
    finally:
        os.close(lock_fd)
        os.unlink(lockpath)


class _Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, set):
            return {"__type__": "set", "__data__": list(o)}
        elif isinstance(o, complex):
            return {"__type__": "complex", "__data__": [o.real, o.imag]}
        elif isinstance(o, datetime.datetime):
            # the sub-second format is used only when needed, so snapshots without microseconds keep
            # the historical format and stay readable by older versions
            fmt = "%Y-%m-%d %H:%M:%S.%f" if o.microsecond else "%Y-%m-%d %H:%M:%S"
            return {"__type__": "datetime", "__data__": o.strftime(fmt)}
        elif "__dict__" in dir(o) and type(o) is not type:
            return {
                "__type__": "instance",
                "__class__": o.__class__.__name__,
                "__module__": o.__class__.__module__,
                "__data__": o.__dict__,
            }
        return json.JSONEncoder.default(self, o)


class _Decoder(json.JSONDecoder):
    def __init__(self):
        json.JSONDecoder.__init__(self, object_hook=self._object_hook)

    def _object_hook(self, decoded):
        if "__type__" in decoded and "__data__" in decoded:
            if decoded["__type__"] == "set":
                return set(decoded["__data__"])
            elif decoded["__type__"] == "complex":
                return complex(decoded["__data__"][0], decoded["__data__"][1])
            elif decoded["__type__"] == "datetime":
                raw = decoded["__data__"]
                fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in raw else "%Y-%m-%d %H:%M:%S"
                return datetime.datetime.strptime(raw, fmt)
            elif decoded["__type__"] == "instance":
                module_name = decoded["__module__"]
                if module_name not in sys.modules:
                    return decoded
                module = sys.modules[module_name]
                target_class = getattr(module, decoded["__class__"], None)
                if target_class is None:
                    return decoded
                instance = target_class.__new__(target_class)
                instance.__dict__ = decoded["__data__"]
                return instance
        return decoded


def _save(name, val):
    tmp = f"{name}.{os.getpid()}.tmp"
    with open(tmp, "w") as file_handle:
        json.dump(val, file_handle, indent=2, separators=(",", ": "), sort_keys=True, cls=_Encoder)
    os.replace(tmp, name)


def _load(name):
    with open(name) as file_handle:
        return json.load(file_handle, cls=_Decoder)


def _name(path, name):
    try:
        return os.path.join(path, f"snap-{name.replace(' ', '_').lower()}.json")
    except (TypeError, AttributeError):
        raise ValueError("failed to create snapshot filename, either bad path or bad name") from None


class SnapshotMixin(_MixinBase):
    """Snapshot mixin.

    Take a snapshot of a python data structure, store it on disk in JSON format, and automatically
    compare the latest data to the stored data on every test run.

    Functional testing (which snapshot testing falls under) is very much blackbox testing.  When
    something goes wrong, it's hard to pinpoint the issue, because functional tests typically
    provide minimal *isolation* as compared to unit tests.  On the plus side, snapshots typically
    do provide enormous *leverage* as a few well-placed snapshot tests can strongly verify that an
    application is working.  Similar coverage would otherwise require dozens if not hundreds of
    unit tests.

    **On-disk Format**

    Snapshots are stored in a readable JSON format.  For example:

        assert_that({'a': 1, 'b': 2, 'c': 3}).snapshot()

    Would be stored as:

        {
            "a": 1,
            "b": 2,
            "c": 3
        }

    The JSON formatting support most python data structures (dict, list, object, etc), but not custom
    binary data.

    **Updating**

    It's easy to update your snapshots...just delete them all and re-run the test suite to regenerate all snapshots.
    Each capture of a new snapshot emits a
    [`SnapshotCreatedWarning`][assertpy2.snapshot.SnapshotCreatedWarning], so a first run is never
    silent (and fails explicitly under ``-W error``).
    """

    def snapshot(
        self,
        id: str | None = None,  # noqa: A002  # `id` is the public snapshot-identifier parameter
        path: str = "__snapshots",
        *,
        ignore: object = None,
        include: object = None,
        tolerance: float | None = None,
        comparators: dict | None = None,
    ) -> Self:
        """Asserts that val is identical to the on-disk snapshot stored previously.

        On the first run of a test before the snapshot file has been saved, a snapshot is created,
        stored to disk, a [`SnapshotCreatedWarning`][assertpy2.snapshot.SnapshotCreatedWarning] is
        emitted, and the test *always* passes.  But on all subsequent runs, val is compared
        to the on-disk snapshot, and the test fails if they don't match.

        Snapshot artifacts are stored in the ``__snapshots`` directory by default, and should be
        committed to source control alongside any code changes.

        Snapshots are identified by test filename plus line number by default.

        The comparison accepts the same selective options as
        [`is_equal_to()`][assertpy2.base.BaseMixin.is_equal_to], so volatile fields (timestamps,
        generated ids) or float noise don't break snapshots.  The snapshot file always stores the
        **full** value; the options only shape the comparison.

        Args:
            id: a custom snapshot identifier (defaults to test filename plus line number)
            path: the directory where snapshots are stored (defaults to ``__snapshots``)

        Keyword Args:
            ignore (Hashable | list | set | frozenset | None): the key/field (or collection of
                keys/fields) to ignore when comparing; accepts the same nested-path tuples,
                ``re.Pattern`` and ``type`` specs as ``is_equal_to()``.
            include (Hashable | list | set | frozenset | None): the key/field (or collection of
                keys/fields) to compare, everything else ignored.
            tolerance (float | None): an absolute tolerance applied to every real-number leaf.
            comparators (dict | None): a dict mapping a ``type`` or a field name to an
                ``(actual, expected) -> bool`` predicate that owns matching leaves.

        Examples:
            Usage:

                assert_that(None).snapshot()
                assert_that(True).snapshot()
                assert_that(1).snapshot()
                assert_that(123.4).snapshot()
                assert_that('foo').snapshot()
                assert_that([1, 2, 3]).snapshot()
                assert_that({'a': 1, 'b': 2, 'c': 3}).snapshot()
                assert_that({'a', 'b', 'c'}).snapshot()
                assert_that(1 + 2j).snapshot()
                assert_that(someobj).snapshot()

            By default, snapshots are identified by test filename plus line number.
            Alternately, you can specify a custom identifier using the ``id`` arg:

                assert_that({'a': 1, 'b': 2, 'c': 3}).snapshot(id='foo-id')


            By default, snapshots are stored in the ``__snapshots`` directory.
            Alternately, you can specify a custom path using the ``path`` arg:

                assert_that({'a': 1, 'b': 2, 'c': 3}).snapshot(path='my-custom-folder')

            Ignore volatile fields, or tolerate float noise, without touching the stored snapshot:

                assert_that(api_response).snapshot(id='order', ignore=['created_at', ('user', 'session_id')])
                assert_that(metrics).snapshot(id='latency', tolerance=0.001)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** equal to on-disk snapshot
            TypeError: if ``tolerance`` is not a real number, or ``comparators`` is not a dict of
                callables (validated on every run, including the capturing first one)
            ValueError: if ``tolerance`` is ``NaN`` or negative

        Warns:
            SnapshotCreatedWarning: when this run captured a new snapshot instead of comparing
        """
        _build_compare_config(tolerance, comparators)  # a bad tolerance must fail the capturing first run too
        lineno = ""
        if id:
            # custom id
            snapname = _name(path, id)
        else:
            # make id from filename and line number
            frame = inspect.currentframe()
            caller = frame.f_back if frame is not None else None
            if caller is None:  # pragma: no cover - frame introspection always available in CPython
                raise RuntimeError("cannot determine caller frame")
            file_path = os.path.basename(caller.f_code.co_filename)
            file_name = os.path.splitext(file_path)[0]
            lineno = str(caller.f_lineno)
            snapname = _name(path, file_name)

        os.makedirs(path, exist_ok=True)

        # Serialize read-modify-write so parallel workers (pytest-xdist) sharing a snap file don't lose
        # each other's entries.  The comparison runs after the lock is released.
        snapshot_value = _UNSET
        with _file_lock(snapname):
            if os.path.isfile(snapname):
                snap = _load(snapname)
                if id:
                    # custom id, so test against the whole file
                    snapshot_value = snap
                elif lineno in snap:
                    # found sub-snap, so test
                    snapshot_value = snap[lineno]
                else:
                    # lineno not in snap, so create sub-snap and pass
                    snap[lineno] = self.val
                    _save(snapname, snap)
            else:
                # no snap, so create and pass
                _save(snapname, self.val if id else {lineno: self.val})

        if snapshot_value is not _UNSET:
            return self.is_equal_to(
                snapshot_value, ignore=ignore, include=include, tolerance=tolerance, comparators=comparators
            )
        warnings.warn(
            f"created snapshot <{snapname}>: this run captured the value instead of comparing;"
            " subsequent runs compare against it (delete the file to re-capture)",
            SnapshotCreatedWarning,
            stacklevel=2,
        )
        return self
