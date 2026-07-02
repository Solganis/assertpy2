from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._compat import Self

__tracebackhide__ = True


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
    ):
        self._func = func
        self._builder_func = builder_func
        self._description = description
        self._timeout = timeout
        self._interval = interval
        self._ignoring = ignoring

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
                deadline = loop.time() + self._timeout
                last_error: Exception | None = None
                while True:
                    try:
                        val = self._func()
                        if inspect.isawaitable(val):
                            val = await val
                        builder = self._builder_func(val, self._description)
                        method = getattr(builder, name)
                        method(*args, **kwargs)
                        return builder
                    except (AssertionError, *self._ignoring) as exc:  # noqa: PERF203  # retry-on-failure needs the try/except per poll iteration
                        last_error = exc
                        if loop.time() >= deadline:
                            # repr for ignored exceptions: their type name is the diagnostic, str() may be empty
                            failure = str(last_error) if isinstance(last_error, AssertionError) else repr(last_error)
                            raise AssertionError(
                                f"Expected condition not met after {self._timeout:.1f} seconds. Last failure: {failure}"
                            ) from last_error
                        await asyncio.sleep(self._interval)

            return _poll()

        return _make_coroutine
