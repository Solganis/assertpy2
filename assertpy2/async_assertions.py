from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Self

__tracebackhide__ = True


class AsyncAssertionBuilder:
    """Async assertion builder that polls a callable until an assertion passes or timeout expires.

    Do not instantiate directly; use :meth:`~assertpy2.assertpy.AssertionBuilder.eventually` instead.

    Args:
        func: a sync or async callable that produces the value to test
        builder_func: factory function to create assertion builders (receives ``val``, ``description``)
        description: optional error description forwarded to the builder
        timeout: maximum seconds to keep retrying
        interval: seconds between retries
    """

    def __init__(
        self,
        func: Callable,
        *,
        builder_func: Callable,
        description: str = "",
        timeout: float = 5.0,
        interval: float = 0.5,
    ):
        self._func = func
        self._builder_func = builder_func
        self._description = description
        self._timeout = timeout
        self._interval = interval

    def within(self, timeout: float) -> Self:
        """Override the timeout (in seconds)."""
        self._timeout = timeout
        return self

    def every(self, interval: float) -> Self:
        """Override the polling interval (in seconds)."""
        self._interval = interval
        return self

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def _make_coroutine(*args, **kwargs):
            async def _poll():
                loop = asyncio.get_running_loop()
                deadline = loop.time() + self._timeout
                last_error: AssertionError | None = None
                while True:
                    try:
                        if inspect.iscoroutinefunction(self._func):
                            val = await self._func()
                        else:
                            val = self._func()
                        builder = self._builder_func(val, self._description)
                        method = getattr(builder, name)
                        method(*args, **kwargs)
                        return builder
                    except AssertionError as exc:
                        last_error = exc
                        if loop.time() >= deadline:
                            raise AssertionError(
                                "Expected condition not met after %.1f seconds. Last failure: %s"
                                % (self._timeout, last_error)
                            ) from last_error
                        await asyncio.sleep(self._interval)

            return _poll()

        return _make_coroutine
