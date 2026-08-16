from __future__ import annotations

import dataclasses
import hashlib
import inspect
import time
from collections import OrderedDict, deque
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from .errors import AssertionFailure, PollSample, PollTrace, _json_safe, _safe_repr, _safe_str

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._engine._compat import Self

__tracebackhide__ = True

_PROBE_UNSET = object()


def _canonical(value: object, _seen: frozenset[int] = frozenset()) -> str:
    """A type-faithful rendering of *value*, with containers ordered where their type has no order.

    Not for reading: this exists so one poll's value can be told from the next's.  JSON was tried first
    and erases exactly what matters here, since `(1,)` and `[1]` both render as `[1]` and a mapping's
    keys all become strings.  A tag carries the container's type instead, and every part is written with
    its own length in front, so nothing a value prints can be read as this rendering's punctuation: a
    leaf whose repr is `[1,2]` used to render exactly as the list `[1, 2]` did.

    Dicts and sets are sorted by their rendered parts: they have no order to preserve, and two equal ones
    can still iterate differently, since a set built from `[0, 8]` and one built from `[8, 0]` collide
    into the same bucket in opposite orders.

    The boundary, since a rendering cannot reproduce `==`: two values that are equal and print
    differently, `1` against `1.0`, count as a change, and two that are unequal and print alike, a
    dataclass hiding a field from its own repr, count as one value.  A leaf carries no type tag of its
    own for the same reason, or a `str` subclass would differ from the string it equals.

    One case cannot be got right by any key of this shape, rather than being a choice made here:
    `OrderedDict([a, b]) == {a: ..., b: ...} == OrderedDict([b, a])` while the two `OrderedDict`s are
    unequal, so Python's own relation is not transitive there and nothing that digests one value at a
    time can follow it.  The ordered pair is the one honoured, because that is where the order carries
    the meaning.
    """
    if id(value) in _seen:
        return "c"  # a container that reaches back to its own root, as `repr` marks with `...`
    inner = _seen | {id(value)}
    if isinstance(value, dict):
        pairs = (_framed(_canonical(k, inner)) + _framed(_canonical(v, inner)) for k, v in value.items())
        # sorted for every mapping but the one whose own `==` reads order: `OrderedDict` is the only
        # mapping in the standard library where two with the same items in another order are unequal,
        # and sorting it turned a real transition into "value unchanged". `isinstance`, not an exact
        # type test, because a subclass inherits that comparison along with the class. `defaultdict` and
        # `Counter` compare like a dict, so they keep the sort rather than reading a reorder as a change
        return "o" + "".join(pairs) if isinstance(value, OrderedDict) else "d" + "".join(sorted(pairs))
    if isinstance(value, (set, frozenset)):
        return "s" + "".join(sorted(_framed(_canonical(member, inner)) for member in value))
    if isinstance(value, tuple):
        return "t" + "".join(_framed(_canonical(member, inner)) for member in value)
    if isinstance(value, list):
        # the tag is redundant for a list once every part carries its length, and it stays for the shape:
        # each branch reads the same way, and a rendering nobody can parse is easier to trust when it is
        # written the same everywhere
        return "l" + "".join(_framed(_canonical(member, inner)) for member in value)
    return "v" + _framed(repr(value))


def _framed(text: str) -> str:
    """*text* with its own length in front, so no rendering can be mistaken for a longer one."""
    return f"{len(text)}:{text}"


def _change_key(value: object) -> str | None:
    """A bounded stand-in for what a probe returned, for deciding whether the value moved.

    ``None`` where no faithful one can be made, which is what stops the summary claiming a value moved,
    or held still, on evidence it does not have.

    Four things have to hold at once.  It must be **complete**, because the sample kept per poll is a
    diagnostic snapshot cut after a hundred items, and comparing those called a queue that grew past its
    hundredth entry unchanged for the rest of the run.  It must be **type-faithful**, since a probe that
    started returning a list where it returned a tuple did change.  It must not depend on **order** a
    value does not have, since two dicts that differ only in insertion order are equal.  And it must
    survive a **live** object, because probes commonly mutate and return the same one, so anything that
    compares the object rather than a rendering of it answers "unchanged" whatever it did.
    """
    try:
        text = _canonical(value)
    except Exception:  # their `__repr__` raised, or their container did when walked
        return None
    return hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=16).hexdigest()


# one call recorded on a polling chain, as (name, args, kwargs); `None` args mark a step that was
# read rather than called, which is `not_`
_Step = tuple[str, "tuple | None", "dict | None"]


_COLLECT_RETRIES: bool = False
"""Whether retried polls are collected at all.

Turned on by the pytest plugin, which is the only consumer: it drains the list per test and reports at
session end.  Off everywhere else (unittest, a plain script, ``-p no:assertpy2``) so nothing accumulates
in a process that would never read it.
"""

_RETRIES: list[tuple[int, float, float]] = []
"""Polls that only passed after retrying, as ``(attempts, elapsed, budget)``.

The recorder already samples every failed poll, so a probe that converges on its third attempt has
already paid for the first two: collecting them costs a list append on a path that has just spent
several sleeps.  Drained by the pytest plugin, which knows which test they belong to.
"""


class _PollRecorder:
    """Collects per-poll samples, collapsing identical runs and keeping the first and last polls."""

    def __init__(self, head: int = 5, tail: int = 20):
        self._head: list[PollSample] = []
        self._head_limit = head
        self._tail: deque[PollSample] = deque(maxlen=tail)
        # the change key of each retained sample, pushed and dropped in lockstep with it. The samples
        # themselves hold the cut snapshot, and reading recurrence off that called five distinct
        # hundred-item lists a cycle between two states, which tells a reader to stop waiting
        self._head_keys: list[str | None] = []
        self._tail_keys: deque[str | None] = deque(maxlen=tail)
        self.dropped = 0
        self.total_polls = 0
        # everything below is counted as it happens, because the window keeps 25 samples and the summary
        # is the headline of the failure: a probe returning a new value on every one of 1337 polls was
        # summarised as "value changed 24 times", which reads as drift where the truth was a value that
        # never settled. Anything the summary states as a fact about the run is recorded here; what it
        # reads off the retained samples is the *shape*, and says so
        self.fail_polls = 0
        self.error_polls = 0
        self.value_changes = 0
        # the same count since the last raising poll, because "value *then* changed" is a claim about
        # what happened after the probe recovered, and a run-wide total answers a different question
        self.changes_after_last_error = 0
        self.uncomparable = False
        self.last_change_elapsed: float | None = None
        self.error_type: type | None = None
        self.mixed_error_types = False
        self.last_outcome: str | None = None
        self._last_fail_key: str | None = None

    def record(self, elapsed, outcome, value, detail, raw=_PROBE_UNSET, error_type=None):
        self.total_polls += 1
        self.last_outcome = outcome
        key = None
        if outcome == "fail":
            self.fail_polls += 1
            # against the last value a poll *returned*, not against the previous poll: a probe that
            # raises in between still moved from A to B, and comparing neighbours called that unchanged.
            # Keyed off the raw value where the caller has one, since the sample it keeps is cut
            key = _change_key(value if raw is _PROBE_UNSET else raw)
            if key is None:
                self.uncomparable = True
            elif self._last_fail_key is not None and key != self._last_fail_key:
                self.value_changes += 1
                self.changes_after_last_error += 1
                self.last_change_elapsed = elapsed
            if key is not None:
                self._last_fail_key = key
        else:  # the only other outcome is "error"
            self.error_polls += 1
            self.changes_after_last_error = 0
            # the type is part of a sentence about every poll, so it cannot come from the samples kept.
            # Two fields rather than a set: the sentence needs "one type" or "several", and a set would
            # be the one thing here that grows with the run the bounded window exists to stop.  Taken
            # the class itself, compared by identity: two classes can share a `__name__`, and the name
            # is for printing. Parsed out of the rendering it was the caller's text deciding our claim
            if error_type is not None:
                if self.error_type is None:
                    self.error_type = error_type
                elif error_type is not self.error_type:
                    self.mixed_error_types = True
        last = self._tail[-1] if self._tail else (self._head[-1] if self._head else None)
        last_key = self._tail_keys[-1] if self._tail_keys else (self._head_keys[-1] if self._head_keys else None)
        # "identical consecutive polls" is decided by the key where there is one, not by the snapshot:
        # two polls whose values differ past the cut are two polls, and collapsing them lost that
        same_value = (
            key == last_key and key is not None if outcome == "fail" else last is not None and last.value == value
        )
        if last is not None and last.outcome == outcome and last.detail == detail and same_value:
            collapsed = dataclasses.replace(last, repeats=last.repeats + 1)
            if self._tail:
                self._tail[-1] = collapsed
            else:
                self._head[-1] = collapsed
            return
        sample = PollSample(elapsed=elapsed, outcome=outcome, value=value, detail=detail)
        if len(self._head) < self._head_limit:
            self._head.append(sample)
            self._head_keys.append(key)
            return
        if len(self._tail) == self._tail.maxlen:
            self.dropped += 1
        self._tail.append(sample)
        self._tail_keys.append(key)

    def build(self, elapsed) -> PollTrace:
        samples = self._head + list(self._tail)
        self.kept_keys = self._head_keys + list(self._tail_keys)
        return PollTrace(
            samples=samples,
            total_polls=self.total_polls,
            dropped=self.dropped,
            elapsed=elapsed,
            summary=_summarize(samples, self, elapsed),
        )


def _summarize(samples, recorder, elapsed) -> str:
    """Classify the convergence trend of a timed-out poll into one diagnostic sentence.

    Every count and every type here comes from the recorder, which saw all of the run.  The retained
    samples are read for one thing only, the *shape* of what repeated, and that sentence names the polls
    it was read from rather than borrowing the run's total.
    """
    total_polls = recorder.total_polls
    if recorder.fail_polls == 0:
        raised = (
            "exceptions" if recorder.mixed_error_types or recorder.error_type is None else recorder.error_type.__name__
        )
        return f"probe raised {raised} on all {total_polls} polls"
    change_word = "time" if recorder.value_changes == 1 else "times"
    if recorder.error_polls:
        poll_word = "poll" if recorder.error_polls == 1 else "polls"
        since = recorder.changes_after_last_error
        # "then" is a claim about what followed the last raising poll, and the run-wide total counts
        # movement that happened before it as well
        if recorder.uncomparable:
            trend = "value could not be compared"
        elif since:
            trend = f"value then changed {since} {'time' if since == 1 else 'times'}"
        else:
            trend = "value then never changed"
        # "recovered" is a claim about order, and the count is a total: a probe that raised, returned a
        # value and raised again ended raising, whatever the totals say
        if recorder.last_outcome == "fail":
            return f"probe recovered after {recorder.error_polls} raising {poll_word}; {trend}"
        return f"probe raised on {recorder.error_polls} of {total_polls} polls; {trend}"
    if recorder.uncomparable:
        # a probe whose values cannot be rendered at all: any count of movement would be one this
        # recorder never took.  Reached only where every poll returned, since a run with raising polls is
        # answered above, and the clause there carries the same admission
        return f"value could not be compared across {total_polls} polls"
    if not recorder.value_changes:
        return f"value unchanged across {total_polls} polls"
    kept = [(sample, key) for sample, key in zip(samples, recorder.kept_keys, strict=True) if sample.outcome == "fail"]
    fails = [sample for sample, _ in kept]
    keys = [key for _, key in kept]
    kept_changes = [right for left, right in pairwise(keys) if left != right]
    distinct = {key for key in keys if key is not None}
    # a simple path through k values takes k-1 changes, so any surplus means the probe came back to a
    # value it already reported: a cycle, which reads nothing like steady progress that ran out of time.
    # Both sides of this are read off the retained samples, so the sentence says which polls it saw:
    # they are collapsed runs, and one of them can stand for many polls
    if len(kept_changes) >= len(distinct):
        kept_polls = sum(sample.repeats for sample in fails)
        over = f"in the {kept_polls} polls kept" if recorder.dropped else f"across {total_polls} polls"
        return f"value cycles between {len(distinct)} states {over}"
    # recorded when it happened rather than read back off the retained samples.  Those two agree today,
    # because a collapsed run keeps the elapsed of its first poll and the newest change is always in the
    # tail, but the agreement rests on both of those and neither is what this sentence is about
    last_change = elapsed - (recorder.last_change_elapsed or 0.0)
    return f"value changed {recorder.value_changes} {change_word}; last change {last_change:.1f}s before the deadline"


def _last_failure_text(exc: BaseException) -> str:
    """The inner failure's headline, without whatever its own rendering would append.

    Outside pytest a failure renders its diff into ``str()``, and the timeout message quotes that text
    while carrying the same diff itself: the reader saw the block twice, once inside the sentence and
    once under it.  Under pytest the plugin turns that rendering off, so the doubling only ever showed
    up where the message is all there is, which is the surface it was added for.
    """
    if isinstance(exc, AssertionFailure):
        # our own class, and the only undecorated form of its message
        return exc._message
    # total on both paths: an ignored exception is one the caller asked to retry past, and reading its
    # `__repr__` is running their code. One that raised escaped the poll instead of being retried
    return _safe_str(exc) if isinstance(exc, AssertionError) else _safe_repr(exc)


def _timeout_failure(recorder: _PollRecorder | None, timeout: float, elapsed: float, failure: str):
    """Build the ``(message, trace)`` pair for a timed-out poll; without a recorder there is no trace."""
    if recorder is None:
        return f"Expected condition not met after {timeout:.1f} seconds. Last failure: {failure}", None
    trace = recorder.build(elapsed)
    message = f"Expected condition not met after {timeout:.1f} seconds ({trace.summary}). Last failure: {failure}"
    return message, trace


def _structured_of(last_error: Exception | None) -> dict[str, Any]:
    """The values and the diff of the assertion that kept failing, as `error()` keyword arguments.

    Only the ones it actually named: `error()` reads "was this named" from whether the argument is there
    at all, so passing everything would put an empty block under every collected timeout.  Which ones
    those were comes from the failure's own record rather than from a test against `None`, because
    `is_equal_to(None)` names an expected value and a probe returning `None` provides an actual one.
    """
    outcome = getattr(last_error, "_outcome", None)
    fields: dict[str, Any] = {}
    if outcome is not None:
        if outcome.actual_provided:
            fields["actual"] = getattr(last_error, "actual", None)
        if outcome.has_expected:
            fields["expected"] = getattr(last_error, "expected", None)
    else:  # built by hand, by a snapshot re-wrap or by `eventually()` itself: the values are all there is
        for name in ("actual", "expected"):
            value = getattr(last_error, name, None)
            if value is not None:
                fields[name] = value
    diff = getattr(last_error, "diff", None)
    if diff is not None:
        fields["diff"] = diff
    return fields


def _timed_out(message: str, trace: PollTrace | None, last_error: Exception | None) -> AssertionFailure:
    """The timeout failure, carrying the structured payload of the assertion that kept failing.

    A polling failure *is* that assertion's failure with a waiting line in front of it, so dropping the
    values and the diff on the way out left the two surfaces unequal where it mattered most: under
    pytest the diff section is built from `exc.diff`, and a timed-out equality printed no section at all
    while the same equality outside a poll printed the full one.

    The record travels with them.  Without it the report falls back to reading "was this named" off a
    test against `None`, which is wrong in both directions: `is_equal_to(None)` lost its expected value,
    a probe returning `None` lost its actual one, and `is_not_empty()`, which names neither, gained a
    block of values nobody asked about.
    """
    failure = AssertionFailure(
        message,
        actual=getattr(last_error, "actual", None),
        expected=getattr(last_error, "expected", None),
        diff=getattr(last_error, "diff", None),
        trace=trace,
    )
    failure._outcome = getattr(last_error, "_outcome", None)
    return failure


def _normalize_ignoring(ignoring) -> tuple[type[Exception], ...]:
    """Normalize an ``ignoring`` spec (one exception type or a tuple of them) to a validated tuple.

    Only ``Exception`` subclasses are accepted, so ``BaseException``-only classes such as
    ``KeyboardInterrupt`` can never be swallowed by the polling loop.
    """
    exceptions = ignoring if isinstance(ignoring, tuple) else (ignoring,)
    for exception_type in exceptions:
        if not (isinstance(exception_type, type) and issubclass(exception_type, Exception)):
            raise TypeError("given ignoring arg must be an Exception subclass or a tuple of Exception subclasses")
    return exceptions


class AsyncAssertionBuilder:
    """Async assertion builder that polls a callable until an assertion passes or timeout expires.

    Do not instantiate directly; use [`eventually()`][assertpy2.assertpy.AssertionBuilder.eventually] instead.

    Args:
        func: a sync or async callable that produces the value to test
        builder_func: factory function to create assertion builders (receives ``val``, ``description``)
        description: optional error description forwarded to the builder
        timeout: maximum seconds to keep retrying
        interval: seconds between retries
        ignoring: exception types the polling loop retries instead of propagating
        kind: the failure mode of the *final* timeout failure (``None``/``"soft"``/``"warn"``);
            polling itself always retries on hard failures
        logger: the logger for ``"warn"`` mode
        trace: record a [`PollTrace`][assertpy2.errors.PollTrace] of the polling timeline
            (default ``True``); ``False`` skips the flight recorder entirely
    """

    def __init__(
        self,
        func: Callable,
        *,
        builder_func: Callable,
        description: str = "",
        timeout: float = 5.0,
        interval: float = 0.5,
        ignoring: tuple[type[Exception], ...] = (),
        kind: str | None = None,
        logger: object = None,
        trace: bool = True,
    ):
        self._func = func
        self._builder_func = builder_func
        self._description = description
        self._timeout = timeout
        self._interval = interval
        self._ignoring = ignoring
        self._kind = kind
        self._logger = logger
        self._trace = trace

    def within(self, timeout: float) -> Self:
        """Override the timeout (in seconds)."""
        self._timeout = timeout
        return self

    def every(self, interval: float) -> Self:
        """Override the polling interval (in seconds)."""
        self._interval = interval
        return self

    def ignoring(self, *exceptions: type[Exception]) -> Self:
        """Replace the exception types the polling loop retries instead of propagating.

        Examples:
            Usage:

                await assert_that(get_order).eventually().within(10).ignoring(ConnectionError).has_status("PAID")

        Raises:
            TypeError: if any argument is not an ``Exception`` subclass
        """
        self._ignoring = _normalize_ignoring(exceptions)
        return self

    def __getattr__(self, name: str) -> Any:
        # `Any` rather than the inferred union: `not_` hands back a builder while every other name hands
        # back a callable, and a checker reading that union refused the call in `eventually_sync().
        # is_equal_to(1)` as "SyncAssertionBuilder is not callable". Found by type-checking third-party
        # code against the built wheel, where it broke chains that had always been valid
        if name.startswith("_"):
            raise AttributeError(name)

        def _make_coroutine(*args, **kwargs):
            async def _poll():
                # deliberately not imported at module level: asyncio costs 21ms of assertpy2's 59ms
                # import, dragging in socket/ssl/select, and only the async polling path needs it.
                # Anyone reaching this line is already inside a running loop, so it is a dict lookup.
                import asyncio

                loop = asyncio.get_running_loop()
                start = loop.time()
                deadline = start + self._timeout
                recorder = _PollRecorder() if self._trace else None
                last_error: Exception | None = None
                while True:
                    probed = _PROBE_UNSET
                    try:
                        val = self._func()
                        if inspect.isawaitable(val):
                            val = await val
                        probed = val
                        builder = self._builder_func(val, self._description)
                        method = getattr(builder, name)
                        method(*args, **kwargs)
                        if _COLLECT_RETRIES and recorder is not None and recorder.total_polls:
                            # it passed, but not on the first look: a probe that only converges after
                            # retrying is the one that goes flaky in CI
                            _RETRIES.append((recorder.total_polls + 1, loop.time() - start, self._timeout))
                        return builder
                    except (
                        AssertionError,
                        *self._ignoring,
                    ) as exc:  # retry-on-failure needs the try/except per poll iteration
                        last_error = exc
                        # repr for ignored exceptions: their type name is the diagnostic, str() may be empty
                        failure = _last_failure_text(exc)
                        if recorder is not None:
                            recorder.record(
                                elapsed=loop.time() - start,
                                # a probe that raised never returned a value, so this is not a value
                                # that failed: `AssertionError` from inside the probe used to be
                                # recorded as one, and a probe that never got past its own assert read
                                # as "value unchanged across N polls"
                                outcome="fail" if probed is not _PROBE_UNSET else "error",
                                # sanitized eagerly: probes often mutate and return the same live object,
                                # so each sample must be a point-in-time snapshot, not a reference
                                value=_json_safe(probed) if probed is not _PROBE_UNSET else None,
                                detail=failure,
                                raw=probed,
                                error_type=None if probed is not _PROBE_UNSET else type(exc),
                            )
                        if loop.time() >= deadline:
                            message, trace = _timeout_failure(recorder, self._timeout, loop.time() - start, failure)
                            if self._kind in ("soft", "warn"):
                                # inner failures already carry the description; an empty one here
                                # avoids a double prefix in the collected/logged message.  the trace goes
                                # with it: a collected timeout kept the text and dropped the telemetry,
                                # and so do the values and the diff, which used to reach the reader only
                                # by being rendered inside the quoted text and so only off pytest
                                return self._builder_func(None, "", self._kind, None, self._logger).error(
                                    message, **_structured_of(last_error), trace=trace
                                )
                            raise _timed_out(message, trace, last_error) from last_error
                        await asyncio.sleep(self._interval)

            return _poll()

        return _make_coroutine


class SyncAssertionBuilder:
    """Blocking assertion builder that polls a sync callable until an assertion passes or timeout expires.

    Do not instantiate directly; use
    [`eventually_sync()`][assertpy2.assertpy.AssertionBuilder.eventually_sync] instead.

    Args:
        func: a sync callable that produces the value to test (an async probe raises ``TypeError``)
        builder_func: factory function to create assertion builders (receives ``val``, ``description``)
        description: optional error description forwarded to the builder
        timeout: maximum seconds to keep retrying
        interval: seconds between retries
        ignoring: exception types the polling loop retries instead of propagating
        kind: the failure mode of the *final* timeout failure (``None``/``"soft"``/``"warn"``);
            polling itself always retries on hard failures
        logger: the logger for ``"warn"`` mode
        trace: record a [`PollTrace`][assertpy2.errors.PollTrace] of the polling timeline
            (default ``True``); ``False`` skips the flight recorder entirely
    """

    def __init__(
        self,
        func: Callable,
        *,
        builder_func: Callable,
        description: str = "",
        timeout: float = 5.0,
        interval: float = 0.5,
        ignoring: tuple[type[Exception], ...] = (),
        kind: str | None = None,
        logger: object = None,
        trace: bool = True,
        steps: tuple[_Step, ...] = (),
        last: Any = None,
    ):
        self._func = func
        self._builder_func = builder_func
        self._description = description
        self._timeout = timeout
        self._interval = interval
        self._ignoring = ignoring
        self._kind = kind
        self._logger = logger
        self._trace = trace
        # every call made on this chain, replayed against a fresh builder on each poll.  Handing back
        # the builder of the last poll instead used to end the polling silently: `.is_instance_of(int)`
        # passed once and returned an ordinary builder, so `.is_equal_to(4)` after it ran against that
        # single snapshot and failed without ever waiting
        self._steps = steps
        self._last = last

    @property
    def val(self) -> object:
        """The value the last passing poll saw.

        Declared on the class rather than left to `__getattr__`, which answers every other name with a
        polling call: reading `.val` off a chain would otherwise poll once and hand back a function.

        Before anything has passed there is no such value, and `__getattr__` says so.  A raise here
        would not: Python falls back to `__getattr__` whenever an attribute lookup ends in
        `AttributeError`, property included, so the message would have been swallowed and answered with
        a polling call all the same.
        """
        return self._last.val

    def _chained(self, steps: tuple[_Step, ...], last: Any = None) -> SyncAssertionBuilder:
        """A copy carrying one more step, so the next call in the chain polls with all of them."""
        return SyncAssertionBuilder(
            self._func,
            builder_func=self._builder_func,
            description=self._description,
            timeout=self._timeout,
            interval=self._interval,
            ignoring=self._ignoring,
            kind=self._kind,
            logger=self._logger,
            trace=self._trace,
            steps=steps,
            last=self._last if last is None else last,
        )

    def within(self, timeout: float) -> Self:
        """Override the timeout (in seconds)."""
        self._timeout = timeout
        return self

    def every(self, interval: float) -> Self:
        """Override the polling interval (in seconds)."""
        self._interval = interval
        return self

    def ignoring(self, *exceptions: type[Exception]) -> Self:
        """Replace the exception types the polling loop retries instead of propagating.

        Examples:
            Usage:

                assert_that(get_order).eventually_sync().within(10).ignoring(ConnectionError).has_status("PAID")

        Raises:
            TypeError: if any argument is not an ``Exception`` subclass
        """
        self._ignoring = _normalize_ignoring(exceptions)
        return self

    def __getattr__(self, name: str) -> Any:
        # `Any` rather than the inferred union: `not_` hands back a builder while every other name hands
        # back a callable, and a checker reading that union refused the call in `eventually_sync().
        # is_equal_to(1)` as "SyncAssertionBuilder is not callable". Found by type-checking third-party
        # code against the built wheel, where it broke chains that had always been valid
        if name.startswith("_"):
            raise AttributeError(name)
        if name == "val":  # reached only when the property above found no poll to read it from
            raise AttributeError("val is available once an assertion on this chain has passed")
        if name == "not_":
            # a property on the builder rather than a call, so there is nothing to poll for yet: it
            # joins the chain and is re-taken on every poll.  Read straight through, it used to hand
            # back this method's inner function, and `.not_.is_equal_to(1)` died on an AttributeError
            return self._chained((*self._steps, (name, None, None)))

        def _run(*args, **kwargs):
            steps = (*self._steps, (name, args, kwargs))
            start = time.monotonic()
            deadline = start + self._timeout
            recorder = _PollRecorder() if self._trace else None
            last_error: Exception | None = None
            while True:
                probed = _PROBE_UNSET
                try:
                    val = self._func()
                    if inspect.isawaitable(val):
                        if inspect.iscoroutine(val):
                            val.close()  # an orphaned coroutine would warn "never awaited" at GC time
                        raise TypeError(
                            "given probe returned an awaitable; use eventually() and await it for async probes"
                        )
                    probed = val
                    builder = self._builder_func(val, self._description)
                    for step, step_args, step_kwargs in steps:
                        attribute = getattr(builder, step)
                        # a step read rather than called, which is `not_`, carries no arguments at all
                        if step_args is None or step_kwargs is None:
                            builder = attribute
                        else:
                            builder = attribute(*step_args, **step_kwargs)
                    if _COLLECT_RETRIES and recorder is not None and recorder.total_polls:
                        _RETRIES.append((recorder.total_polls + 1, time.monotonic() - start, self._timeout))
                    return self._chained(steps, builder)
                except (
                    AssertionError,
                    *self._ignoring,
                ) as exc:  # retry-on-failure needs the try/except per poll iteration
                    last_error = exc
                    # repr for ignored exceptions: their type name is the diagnostic, str() may be empty
                    failure = _last_failure_text(exc)
                    if recorder is not None:
                        recorder.record(
                            elapsed=time.monotonic() - start,
                            # as in the async branch: an exception from the probe is not a failed value
                            outcome="fail" if probed is not _PROBE_UNSET else "error",
                            # sanitized eagerly: probes often mutate and return the same live object,
                            # so each sample must be a point-in-time snapshot, not a reference
                            value=_json_safe(probed) if probed is not _PROBE_UNSET else None,
                            detail=failure,
                            raw=probed,
                            error_type=None if probed is not _PROBE_UNSET else type(exc),
                        )
                    if time.monotonic() >= deadline:
                        message, trace = _timeout_failure(recorder, self._timeout, time.monotonic() - start, failure)
                        if self._kind in ("soft", "warn"):
                            # as in the async branch above: the values and the diff travel with the
                            # message rather than only inside the text it quotes
                            return self._builder_func(None, "", self._kind, None, self._logger).error(
                                message, **_structured_of(last_error), trace=trace
                            )
                        raise _timed_out(message, trace, last_error) from last_error
                    time.sleep(self._interval)

        return _run
