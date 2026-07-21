from __future__ import annotations

import asyncio
import dataclasses
import inspect
import time
from collections import deque
from itertools import pairwise
from typing import TYPE_CHECKING

from .errors import AssertionFailure, PollSample, PollTrace, _json_safe

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._engine._compat import Self

__tracebackhide__ = True

_PROBE_UNSET = object()


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
        self.dropped = 0
        self.total_polls = 0
        self.fail_polls = 0  # counted across all polls, not just the retained window
        self.error_polls = 0

    def record(self, elapsed, outcome, value, detail):
        self.total_polls += 1
        if outcome == "fail":
            self.fail_polls += 1
        else:  # the only other outcome is "error"
            self.error_polls += 1
        last = self._tail[-1] if self._tail else (self._head[-1] if self._head else None)
        if last is not None and (last.outcome, last.value, last.detail) == (outcome, value, detail):
            collapsed = dataclasses.replace(last, repeats=last.repeats + 1)
            if self._tail:
                self._tail[-1] = collapsed
            else:
                self._head[-1] = collapsed
            return
        sample = PollSample(elapsed=elapsed, outcome=outcome, value=value, detail=detail)
        if len(self._head) < self._head_limit:
            self._head.append(sample)
            return
        if len(self._tail) == self._tail.maxlen:
            self.dropped += 1
        self._tail.append(sample)

    def build(self, elapsed) -> PollTrace:
        samples = self._head + list(self._tail)
        return PollTrace(
            samples=samples,
            total_polls=self.total_polls,
            dropped=self.dropped,
            elapsed=elapsed,
            summary=_summarize(samples, self.total_polls, elapsed, self.fail_polls, self.error_polls),
        )


def _summarize(samples, total_polls, elapsed, fail_polls, error_polls) -> str:
    """Classify the convergence trend of a timed-out poll into one diagnostic sentence.

    ``fail_polls``/``error_polls`` count every poll, not just the retained samples, so the summary
    stays correct even when the bounded window dropped some fail samples.
    """
    if fail_polls == 0:
        types = {sample.detail.split("(", 1)[0] for sample in samples}
        raised = types.pop() if len(types) == 1 else "exceptions"
        return f"probe raised {raised} on all {total_polls} polls"
    fails = [sample for sample in samples if sample.outcome == "fail"]
    changes = [current for previous, current in pairwise(fails) if current.value != previous.value]
    change_word = "time" if len(changes) == 1 else "times"
    if error_polls:
        poll_word = "poll" if error_polls == 1 else "polls"
        trend = f"value then changed {len(changes)} {change_word}" if changes else "value then never changed"
        return f"probe recovered after {error_polls} raising {poll_word}; {trend}"
    if not changes:
        return f"value unchanged across {total_polls} polls"
    distinct: list[object] = []
    for sample in fails:
        if not any(sample.value == seen for seen in distinct):
            distinct.append(sample.value)
    # a simple path through k values takes k-1 changes, so any surplus means the probe came back to a
    # value it already reported: a cycle, which reads nothing like steady progress that ran out of time
    if len(changes) >= len(distinct):
        return f"value cycles between {len(distinct)} states across {total_polls} polls"
    last_change = elapsed - changes[-1].elapsed
    return f"value changed {len(changes)} {change_word}; last change {last_change:.1f}s before the deadline"


def _timeout_failure(recorder: _PollRecorder | None, timeout: float, elapsed: float, failure: str):
    """Build the ``(message, trace)`` pair for a timed-out poll; without a recorder there is no trace."""
    if recorder is None:
        return f"Expected condition not met after {timeout:.1f} seconds. Last failure: {failure}", None
    trace = recorder.build(elapsed)
    message = f"Expected condition not met after {timeout:.1f} seconds ({trace.summary}). Last failure: {failure}"
    return message, trace


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

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def _make_coroutine(*args, **kwargs):
            async def _poll():
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
                        failure = str(exc) if isinstance(exc, AssertionError) else repr(exc)
                        if recorder is not None:
                            recorder.record(
                                elapsed=loop.time() - start,
                                outcome="fail" if isinstance(exc, AssertionError) else "error",
                                # sanitized eagerly: probes often mutate and return the same live object,
                                # so each sample must be a point-in-time snapshot, not a reference
                                value=_json_safe(probed) if probed is not _PROBE_UNSET else None,
                                detail=failure,
                            )
                        if loop.time() >= deadline:
                            message, trace = _timeout_failure(recorder, self._timeout, loop.time() - start, failure)
                            if self._kind in ("soft", "warn"):
                                # inner failures already carry the description; an empty one here
                                # avoids a double prefix in the collected/logged message
                                return self._builder_func(None, "", self._kind, None, self._logger).error(message)
                            raise AssertionFailure(message, trace=trace) from last_error
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

                assert_that(get_order).eventually_sync().within(10).ignoring(ConnectionError).has_status("PAID")

        Raises:
            TypeError: if any argument is not an ``Exception`` subclass
        """
        self._ignoring = _normalize_ignoring(exceptions)
        return self

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def _run(*args, **kwargs):
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
                    method = getattr(builder, name)
                    method(*args, **kwargs)
                    if _COLLECT_RETRIES and recorder is not None and recorder.total_polls:
                        _RETRIES.append((recorder.total_polls + 1, time.monotonic() - start, self._timeout))
                    return builder
                except (
                    AssertionError,
                    *self._ignoring,
                ) as exc:  # retry-on-failure needs the try/except per poll iteration
                    last_error = exc
                    # repr for ignored exceptions: their type name is the diagnostic, str() may be empty
                    failure = str(exc) if isinstance(exc, AssertionError) else repr(exc)
                    if recorder is not None:
                        recorder.record(
                            elapsed=time.monotonic() - start,
                            outcome="fail" if isinstance(exc, AssertionError) else "error",
                            # sanitized eagerly: probes often mutate and return the same live object,
                            # so each sample must be a point-in-time snapshot, not a reference
                            value=_json_safe(probed) if probed is not _PROBE_UNSET else None,
                            detail=failure,
                        )
                    if time.monotonic() >= deadline:
                        message, trace = _timeout_failure(recorder, self._timeout, time.monotonic() - start, failure)
                        if self._kind in ("soft", "warn"):
                            # inner failures already carry the description; an empty one here
                            # avoids a double prefix in the collected/logged message
                            return self._builder_func(None, "", self._kind, None, self._logger).error(message)
                        raise AssertionFailure(message, trace=trace) from last_error
                    time.sleep(self._interval)

        return _run
