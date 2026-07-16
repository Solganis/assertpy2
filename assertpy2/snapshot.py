from __future__ import annotations

import contextlib
import inspect
import os
import time
import warnings
from typing import TYPE_CHECKING, Final

from . import _inline
from ._compare import _build_compare_config
from ._contract import shape, shape_diff
from ._mixin_base import _MixinBase
from ._snapshot_codec import _SERIALIZERS, _load, _save, _Serializer
from .errors import _truncated
from .matchers import _apply_matcher, _describe_matcher, _is_matcher

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from ._compat import Self

__tracebackhide__ = True

_UNSET: Final = object()


def register_snapshot_serializer(
    cls: type,
    encode: Callable[[object], object],
    decode: Callable[[object], object],
    *,
    tag: str | None = None,
) -> None:
    """Register a custom (encode, decode) pair for snapshotting values of type ``cls``.

    The typed codec covers common non-JSON types (``set``, ``complex``, ``datetime``/``date``/``time``,
    ``Decimal``, ``bytes``, ``uuid.UUID``, ``Enum``); register a serializer for anything else - a
    domain object, an ORM row, a ``pathlib.Path`` - so ``snapshot()`` stores and round-trips it instead
    of raising ``TypeError``.  Matching is by ``isinstance`` (so subclasses are covered), the registry
    is consulted **before** the built-ins, and a later registration wins over an earlier one for
    overlapping types.

    Args:
        cls: the type (matched by ``isinstance``) the serializer applies to
        encode: ``value -> json_safe`` (the returned object must itself be JSON-serializable or
            handled by another serializer)
        decode: ``json_safe -> value`` (the inverse; runs your own code on snapshot load, so it is a
            trusted, explicit opt-in - unlike the automatic instance decode, which never imports)
        tag: a stable identifier stored in the snapshot to route decoding (defaults to the type's
            fully-qualified name); change it only deliberately, since existing snapshots key on it

    Examples:
        Usage:

            import pathlib

            register_snapshot_serializer(pathlib.PurePath, str, pathlib.PurePath)

    Raises:
        TypeError: if ``cls`` is not a type, or ``encode`` / ``decode`` are not callable
    """
    if not isinstance(cls, type):
        raise TypeError("cls must be a type")
    if not callable(encode) or not callable(decode):
        raise TypeError("encode and decode must be callable")
    _SERIALIZERS.insert(0, _Serializer(cls, encode, decode, tag or f"{cls.__module__}.{cls.__qualname__}"))


class SnapshotCreatedWarning(UserWarning):
    """Emitted when `snapshot()` writes a new snapshot instead of comparing.

    The first run of a snapshot assertion captures the current value and passes without comparing
    anything, so a wrong first capture would silently become the reference.  This warning makes that
    capture visible; suites running with ``-W error`` turn it into an explicit failure.
    """


class SnapshotUpdatedWarning(UserWarning):
    """Emitted when `snapshot()` overwrites a stored snapshot in update mode.

    Update mode (the ``--assertpy2-snapshot-update`` pytest flag, or the
    ``ASSERTPY2_SNAPSHOT_UPDATE`` environment variable) replaces failing snapshots with the current
    value instead of failing.  Each overwrite emits this warning, so an update run reports exactly
    which snapshots changed instead of rewriting them silently.
    """


# set by the pytest plugin when --assertpy2-snapshot-update is given; the env var covers other runners
_UPDATE_ALL: bool = False

# tri-state CI mode set by the pytest plugin flags (None = not set by a flag)
_CI_MODE: bool | None = None

# (snapname, key) pairs touched this session; key is the lineno for a default-id sub-snap, or "" for a
# whole-file custom-id snapshot. The pytest plugin reads this at session finish to report obsolete
# snapshots (xdist workers ship their sets to the controller).
_TOUCHED: set[tuple[str, str]] = set()

_TRUTHY: Final = frozenset({"1", "true", "yes", "on"})
_FALSY: Final = frozenset({"0", "false", "no", "off"})


def _update_enabled() -> bool:
    return _UPDATE_ALL or os.environ.get("ASSERTPY2_SNAPSHOT_UPDATE", "").strip().lower() in _TRUTHY


def _ci_mode_enabled() -> bool:
    """Whether snapshot creation is forbidden (a missing snapshot fails instead of being created).

    Precedence: the pytest ``--assertpy2-snapshot-ci`` / ``--assertpy2-snapshot-no-ci`` flags, then the
    ``ASSERTPY2_SNAPSHOT_CI`` env var (explicit on/off), then autodetection of a CI environment (a
    truthy ``CI`` var, set by GitHub Actions, GitLab CI, CircleCI, and most others).
    """
    if _CI_MODE is not None:
        return _CI_MODE
    explicit = os.environ.get("ASSERTPY2_SNAPSHOT_CI", "").strip().lower()
    if explicit in _FALSY:
        return False
    if explicit in _TRUTHY:
        return True
    return os.environ.get("CI", "").strip().lower() in _TRUTHY


def _forbid_creation_in_ci(snapname: str) -> None:
    """In CI mode a missing snapshot is a hard failure, not a silent create - the golden was never
    committed, so drift detection for this test would be silently off."""
    if _ci_mode_enabled():
        raise AssertionError(
            f"snapshot <{snapname}> does not exist and CI mode forbids creating it - commit the snapshot"
            " to source control, or run without CI mode (--assertpy2-snapshot-no-ci, or unset CI /"
            " ASSERTPY2_SNAPSHOT_CI)"
        )


def _inline_literal_or_raise(value: object) -> None:
    """Reject values that cannot round-trip as a source literal (an inline snapshot rewrites source)."""
    if not _inline.is_literalable(value):
        raise TypeError(
            "an inline snapshot literal must be a dict/list/tuple/set of scalars, not"
            f" {type(value).__name__} - use snapshot() to store it in a file instead"
        )


def _combine_ignore(ignore, placeholders):
    """Merge the placeholder keys into the caller's ``ignore`` spec, so token fields are skipped by the
    equality comparison (their matcher is asserted separately)."""
    if not placeholders:
        return ignore
    keys = list(placeholders)
    if ignore is None:
        return keys
    if isinstance(ignore, (list, set, frozenset)):
        return [*keys, *ignore]
    return [*keys, ignore]  # a single key or a nested-path tuple


def _find_orphans(touched):
    """Given the ``(snapname, key)`` pairs touched this session, return obsolete snapshots as
    ``(sub_key_orphans, whole_file_orphans)``.

    A sub-key orphan is ``(snapname, lineno)`` still on disk in a *touched* default-id file whose test
    line was not exercised this run (that specific test was deleted).  A whole-file orphan is a snapshot
    file in a touched directory that was not touched at all (its test/module is gone).  Only directories
    that had at least one live snapshot this run are scanned, so an unrelated directory is never judged.
    """
    touched_files = {snapname for snapname, _ in touched}
    custom_touched = {snapname for snapname, key in touched if key == ""}
    touched_keys: dict[str, set[str]] = {}
    for snapname, key in touched:
        if key != "":
            touched_keys.setdefault(snapname, set()).add(key)

    sub_orphans: list[tuple[str, str]] = []
    whole_orphans: list[str] = []
    for directory in sorted({os.path.dirname(snapname) for snapname, _ in touched}):
        if not os.path.isdir(directory):
            continue
        for fname in sorted(os.listdir(directory)):
            if not (fname.startswith("snap-") and fname.endswith(".json")):
                continue
            snapname = os.path.join(directory, fname)
            if snapname not in touched_files:
                whole_orphans.append(snapname)
                continue
            if snapname in custom_touched:
                continue  # a touched whole-file custom-id snapshot is live
            data = _load(snapname)
            live = touched_keys.get(snapname, set())
            sub_orphans.extend((snapname, key) for key in sorted(data) if key not in live)
    return sub_orphans, whole_orphans


def _prune_sub_key_orphans(sub_orphans):
    """Remove obsolete sub-snap keys from their files, deleting a file that becomes empty."""
    by_file: dict[str, set[str]] = {}
    for snapname, key in sub_orphans:
        by_file.setdefault(snapname, set()).add(key)
    for snapname, keys in by_file.items():
        with _file_lock(snapname):
            data = _load(snapname)
            for key in keys:
                data.pop(key, None)
            if data:
                _save(snapname, data)
            else:
                os.unlink(snapname)


@contextlib.contextmanager
def _file_lock(target: str, *, timeout: float = 10.0, poll: float = 0.05) -> Iterator[None]:
    """Serialize snapshot read-modify-write across processes via an ``O_EXCL`` lock file.

    Not crash-safe: a process that dies while holding the lock leaves a stale lock file and other
    writers time out.  Accepted: snapshots are development-time files and crashes mid-write are rare.
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


def _name(path, name):
    try:
        return os.path.join(path, f"snap-{name.replace(' ', '_').lower()}.json")
    except (TypeError, AttributeError):
        raise ValueError("failed to create snapshot filename, either bad path or bad name") from None


def _format_shape_drift(drift):
    """Render `shape_diff` entries as an aligned added/removed/retyped report."""
    glyph = {"added": "+", "removed": "-", "retyped": "~"}
    return "\n".join(f"  {glyph[kind]} {where} {detail}".rstrip() for kind, where, detail in drift)


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

    The JSON formatting supports most python data structures (dict, list, object, etc).  Values
    without a native JSON form round-trip through typed markers: ``set``, ``complex``,
    ``datetime.datetime`` (including timezone-aware), ``datetime.date``, ``datetime.time``,
    ``decimal.Decimal``, ``bytes`` (stored base64-encoded), ``uuid.UUID``, and ``Enum`` members.
    Any other type can be handled by registering a serializer with
    [`register_snapshot_serializer()`][assertpy2.snapshot.register_snapshot_serializer].

    **Updating**

    Run pytest with ``--assertpy2-snapshot-update`` (or set the ``ASSERTPY2_SNAPSHOT_UPDATE``
    environment variable for other runners) and every failing snapshot comparison overwrites the
    stored value instead of failing, each emitting a
    [`SnapshotUpdatedWarning`][assertpy2.snapshot.SnapshotUpdatedWarning].  Matching snapshots are
    left untouched.  Deleting the snapshot files and re-running still works too - each fresh capture
    emits a [`SnapshotCreatedWarning`][assertpy2.snapshot.SnapshotCreatedWarning], so neither a first
    run nor an update run is ever silent (and both fail explicitly under ``-W error``).

    **CI mode**

    On a first run a missing snapshot is *created* and the test passes - convenient locally, but a
    hazard in CI: a snapshot test whose golden was never committed would create it in the ephemeral
    workspace, pass, and silently disable drift detection for that test.  In CI mode a missing
    snapshot is instead a hard failure.  Enable it with the ``--assertpy2-snapshot-ci`` pytest flag
    or the ``ASSERTPY2_SNAPSHOT_CI`` environment variable; it is also auto-enabled when a ``CI``
    environment variable is set (the near-universal CI marker).  Disable the autodetection with
    ``--assertpy2-snapshot-no-ci`` or ``ASSERTPY2_SNAPSHOT_CI=0``.  Local runs are unaffected.
    """

    def _with_placeholder_tokens(self, placeholders):
        """A shallow copy of the dict-like val with placeholder keys replaced by descriptive tokens, so
        the stored snapshot documents the expected shape instead of a volatile captured value."""
        stored = dict(self.val)
        for key, matcher in placeholders.items():
            stored[key] = {"__placeholder__": _describe_matcher(matcher)}
        return stored

    def _check_placeholders(self, placeholders) -> None:
        """Assert each placeholder field of val is present and satisfies its matcher (shape, not value)."""
        for key, matcher in placeholders.items():
            present = key in self.val
            if not present or not _apply_matcher(matcher, self.val[key]):
                actual = repr(self.val[key]) if present else "missing"
                self.error(
                    f"Expected snapshot placeholder <{key}> to satisfy {_describe_matcher(matcher)}, but was {actual}."
                )

    def _snapshot_stale(self, snapshot_value, *, ignore, include, tolerance, comparators) -> bool:
        """Whether the stored snapshot no longer matches val, decided via a strict throwaway builder
        (under soft/warn kinds ``self.is_equal_to`` would not raise)."""
        try:
            self.builder(self.val, "").is_equal_to(
                snapshot_value, ignore=ignore, include=include, tolerance=tolerance, comparators=comparators
            )
        except AssertionError:
            return True
        return False

    def snapshot(
        self,
        id: str | None = None,  # noqa: A002  # `id` is the public snapshot-identifier parameter
        path: str = "__snapshots",
        *,
        ignore: object = None,
        include: object = None,
        tolerance: float | None = None,
        comparators: dict | None = None,
        placeholders: dict | None = None,
    ) -> Self:
        """Asserts that val is identical to the on-disk snapshot stored previously.

        On the first run of a test before the snapshot file has been saved, a snapshot is created,
        stored to disk, a [`SnapshotCreatedWarning`][assertpy2.snapshot.SnapshotCreatedWarning] is
        emitted, and the test *always* passes.  But on all subsequent runs, val is compared
        to the on-disk snapshot, and the test fails if they don't match.

        Snapshot artifacts are stored in the ``__snapshots`` directory by default, and should be
        committed to source control alongside any code changes.

        Snapshots are identified by test filename plus line number by default.

        In update mode (the ``--assertpy2-snapshot-update`` pytest flag, or the
        ``ASSERTPY2_SNAPSHOT_UPDATE`` environment variable) a failing comparison overwrites the
        stored snapshot with the current value and passes, emitting a
        [`SnapshotUpdatedWarning`][assertpy2.snapshot.SnapshotUpdatedWarning]; a matching snapshot
        is left untouched.

        In CI mode (the ``--assertpy2-snapshot-ci`` pytest flag, the ``ASSERTPY2_SNAPSHOT_CI``
        environment variable, or an auto-detected ``CI`` environment) a *missing* snapshot is a hard
        ``AssertionError`` instead of being created and passing, so an uncommitted golden fails the
        build rather than silently disabling drift detection.

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
            placeholders (dict | None): a dict mapping a top-level key of a *dict-like* val to a
                ``Matcher`` (or callable predicate).  The stored snapshot records a descriptive token
                (``Any<...>``) for that field instead of the volatile value, and the comparison asserts
                the actual field satisfies the matcher (presence + shape) rather than exact equality -
                so a generated id or timestamp reads as its shape in the golden and never breaks it.

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

            Store a shape token for a volatile field, and assert its shape on every run:

                from assertpy2 import match

                assert_that(response).snapshot(id='order', placeholders={'id': match.is_uuid()})
                # stored as {"id": {"__placeholder__": "a valid UUID string"}, ...}

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** equal to on-disk snapshot
            TypeError: if ``tolerance`` is not a real number, or ``comparators`` is not a dict of
                callables (validated on every run, including the capturing first one); or if
                ``placeholders`` is given for a non-dict-like val, or maps to a non-matcher value
            ValueError: if ``tolerance`` is ``NaN`` or negative

        Warns:
            SnapshotCreatedWarning: when this run captured a new snapshot instead of comparing
            SnapshotUpdatedWarning: when update mode overwrote a stale snapshot instead of failing
        """
        _build_compare_config(tolerance, comparators)  # a bad tolerance must fail the capturing first run too
        if placeholders:
            self._require_dict_like(self.val, name="val")  # placeholders address keys of a dict-like value
            for matcher in placeholders.values():
                if not _is_matcher(matcher) and not callable(matcher):
                    raise TypeError("placeholder values must be Matcher instances or callables")
        # the stored snapshot documents placeholders as tokens; the comparison ignores those keys and
        # asserts their matcher separately, so a volatile field never breaks the snapshot
        stored_val = self._with_placeholder_tokens(placeholders) if placeholders else self.val
        effective_ignore = _combine_ignore(ignore, placeholders)
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

        _TOUCHED.add((snapname, "" if id else lineno))
        os.makedirs(path, exist_ok=True)

        # Serialize read-modify-write so parallel workers (pytest-xdist) sharing a snap file don't lose
        # each other's entries.  The normal comparison runs after the lock is released; the update-mode
        # rewrite decision must stay inside it.
        snapshot_value = _UNSET
        updated = False
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
                    _forbid_creation_in_ci(snapname)
                    snap[lineno] = stored_val
                    _save(snapname, snap)

                if (
                    snapshot_value is not _UNSET
                    and _update_enabled()
                    and self._snapshot_stale(
                        snapshot_value,
                        ignore=effective_ignore,
                        include=include,
                        tolerance=tolerance,
                        comparators=comparators,
                    )
                ):
                    if id:
                        _save(snapname, stored_val)
                    else:
                        snap[lineno] = stored_val
                        _save(snapname, snap)
                    updated = True
            else:
                # no snap, so create and pass
                _forbid_creation_in_ci(snapname)
                _save(snapname, stored_val if id else {lineno: stored_val})

        if updated:
            warnings.warn(
                f"updated snapshot <{snapname}>: this run overwrote the stored value instead of comparing;"
                " subsequent runs compare against it",
                SnapshotUpdatedWarning,
                stacklevel=2,
            )
            return self
        if snapshot_value is not _UNSET:
            if placeholders:
                self._check_placeholders(placeholders)
            return self.is_equal_to(
                snapshot_value, ignore=effective_ignore, include=include, tolerance=tolerance, comparators=comparators
            )
        warnings.warn(
            f"created snapshot <{snapname}>: this run captured the value instead of comparing;"
            " subsequent runs compare against it (delete the file to re-capture)",
            SnapshotCreatedWarning,
            stacklevel=2,
        )
        return self

    def matches_inline(
        self,
        expected: object = _UNSET,
        *,
        ignore: object = None,
        include: object = None,
        tolerance: float | None = None,
        comparators: dict[object, Callable[..., bool]] | None = None,
        placeholders: dict[object, object] | None = None,
    ) -> Self:
        """Asserts that val equals an inline snapshot literal written at the call site.

        Unlike [`snapshot()`][assertpy2.snapshot.SnapshotMixin.snapshot], which stores the value in a
        separate file, an inline snapshot lives as a literal argument in the test source. Call it empty
        the first time and run with ``--assertpy2-snapshot-update`` to record the value into the source;
        later runs compare against it. The same selective knobs as ``snapshot()`` apply, so volatile
        fields never make the snapshot brittle.

        The comparison itself is an ordinary equality check with no source introspection, so it works
        under ``pytest-xdist`` and needs neither the ``[inline]`` extra nor any assertion rewriting;
        only recording (empty call under update mode) reads the source.

        Args:
            expected: the recorded literal; omit it to record on the next update run.
            ignore: key(s)/path(s) to skip in the comparison (as in ``is_equal_to``).
            include: restrict the comparison to these key(s)/path(s).
            tolerance: absolute numeric tolerance applied at every depth.
            comparators: per-type custom equality callables.
            placeholders: ``{key: matcher}`` for volatile fields - the key is ignored by the equality
                comparison and its matcher asserted separately.

        Examples:
            Usage:

                assert_that({"id": 1, "name": "Alice"}).matches_inline({"id": 1, "name": "Alice"})

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not equal the recorded literal, or the snapshot is still empty
        """
        if placeholders:
            self._require_dict_like(self.val, name="val")  # placeholders address keys of a dict-like value
            for matcher in placeholders.values():
                if not _is_matcher(matcher) and not callable(matcher):
                    raise TypeError("placeholder values must be Matcher instances or callables")
        if expected is _UNSET:
            if _ci_mode_enabled():
                raise AssertionError(
                    "inline snapshot is empty and CI mode forbids recording it - record it locally with"
                    " --assertpy2-snapshot-update and commit the source"
                )
            if _update_enabled():
                _inline_literal_or_raise(self.val)
                frame = inspect.currentframe()
                caller = frame.f_back if frame is not None else None
                if caller is None:  # pragma: no cover - frame introspection always available in CPython
                    raise RuntimeError("cannot determine caller frame")
                _inline.record_create(caller, self.val)
                warnings.warn(
                    "recorded inline snapshot: this run captured the value into the test source;"
                    " subsequent runs compare against it",
                    SnapshotCreatedWarning,
                    stacklevel=2,
                )
                return self
            raise AssertionError("inline snapshot is empty; run --assertpy2-snapshot-update to record it")

        effective_ignore = _combine_ignore(ignore, placeholders)
        if _update_enabled() and self._snapshot_stale(
            expected, ignore=effective_ignore, include=include, tolerance=tolerance, comparators=comparators
        ):
            _inline_literal_or_raise(self.val)
            frame = inspect.currentframe()
            caller = frame.f_back if frame is not None else None
            if caller is None:  # pragma: no cover - frame introspection always available in CPython
                raise RuntimeError("cannot determine caller frame")
            _inline.record_update(caller, self.val)
            warnings.warn(
                "updated inline snapshot: this run overwrote the stored literal instead of comparing;"
                " subsequent runs compare against it",
                SnapshotUpdatedWarning,
                stacklevel=2,
            )
            return self
        if placeholders:
            self._check_placeholders(placeholders)
        return self.is_equal_to(
            expected, ignore=effective_ignore, include=include, tolerance=tolerance, comparators=comparators
        )

    def matches_contract_snapshot(self, id: str | None = None, path: str = "__snapshots") -> Self:  # noqa: A002  # `id` is the public snapshot-identifier parameter
        """Asserts that val's *structure* matches a contract snapshot stored previously.

        Records the shape - paths and type categories, never values - on the first run, then on later
        runs fails only on **structural** drift: a field added, removed, or retyped.  It is value-tolerant
        by construction, so dynamic ids, timestamps, and amounts change freely without breaking the
        snapshot, and it needs no hand-written model - the contract is inferred from the first response.
        Numbers are one category (``5`` and ``5.0`` do not drift) and a ``null`` sample is a nullable
        wildcard.

        The model-driven counterpart is
        [`assert_conforms(..., exact=True)`][assertpy2.assertpy.assert_conforms]: reach for that when you
        already have a pydantic model, and for this when you would rather capture the shape from a real
        response.

        Honors the same update mode (``--assertpy2-snapshot-update``), CI mode
        (``--assertpy2-snapshot-ci``), and storage layout as
        [`snapshot()`][assertpy2.snapshot.SnapshotMixin.snapshot].  Because a contract is inferred from a
        single observation it cannot know which fields are optional, so a legitimately sometimes-absent
        field reads as ``removed``; re-record with update mode when the contract really changed.

        Args:
            id: a custom snapshot identifier (defaults to test filename plus line number)
            path: the directory where snapshots are stored (defaults to ``__snapshots``)

        Examples:
            Usage:

                assert_that(response.json()).matches_contract_snapshot()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's structure drifts from the stored contract snapshot

        Warns:
            SnapshotCreatedWarning: when this run captured a new contract instead of comparing
            SnapshotUpdatedWarning: when update mode overwrote a drifted contract instead of failing
        """
        contract = shape(self.val)
        lineno = ""
        if id:
            snapname = _name(path, id)
        else:
            frame = inspect.currentframe()
            caller = frame.f_back if frame is not None else None
            if caller is None:  # pragma: no cover - frame introspection always available in CPython
                raise RuntimeError("cannot determine caller frame")
            file_name = os.path.splitext(os.path.basename(caller.f_code.co_filename))[0]
            lineno = str(caller.f_lineno)
            snapname = _name(path, file_name)

        _TOUCHED.add((snapname, "" if id else lineno))
        os.makedirs(path, exist_ok=True)

        stored = _UNSET
        updated = False
        with _file_lock(snapname):
            if os.path.isfile(snapname):
                snap = _load(snapname)
                if id:
                    stored = snap
                elif lineno in snap:
                    stored = snap[lineno]
                else:
                    _forbid_creation_in_ci(snapname)
                    snap[lineno] = contract
                    _save(snapname, snap)

                if stored is not _UNSET and _update_enabled() and shape_diff(stored, contract):
                    if id:
                        _save(snapname, contract)
                    else:
                        snap[lineno] = contract
                        _save(snapname, snap)
                    updated = True
            else:
                _forbid_creation_in_ci(snapname)
                _save(snapname, contract if id else {lineno: contract})

        if updated:
            warnings.warn(
                f"updated contract snapshot <{snapname}>: this run overwrote the stored shape instead of"
                " comparing; subsequent runs compare against it",
                SnapshotUpdatedWarning,
                stacklevel=2,
            )
            return self
        if stored is not _UNSET:
            drift = shape_diff(stored, contract)
            if drift:
                return self.error(
                    f"Expected <{_truncated(str(self.val))}> to match contract snapshot <{snapname}>, but the structure"
                    f" drifted:\n{_format_shape_drift(drift)}",
                    actual=self.val,
                )
            return self
        warnings.warn(
            f"created contract snapshot <{snapname}>: this run captured the shape instead of comparing;"
            " subsequent runs compare against it (delete the file to re-capture)",
            SnapshotCreatedWarning,
            stacklevel=2,
        )
        return self
