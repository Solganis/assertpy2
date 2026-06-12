# Copyright (c) 2015-2019, Activision Publishing, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import Self

__tracebackhide__ = True


class _InertBuilder:
    """No-op builder returned after a failed raises/when_called_with in soft mode.

    Silently absorbs all chained assertions so they don't crash on wrong val type.
    """

    def __getattr__(self, name):
        return lambda *args, **kwargs: self


class ExceptionMixin:
    """Expected exception mixin."""

    def raises(self, ex) -> Self:
        """Asserts that val is callable and set the expected exception.

        Just sets the expected exception, but never calls val, and therefore never failes. You must
        chain to :meth:`~when_called_with` to invoke ``val()``.

        Args:
            ex: the expected exception

        Examples:
            Usage::

                assert_that(some_func).raises(RuntimeError).when_called_with('foo')

        Returns:
            AssertionBuilder: returns a new instance (now with the given expected exception) to chain to the next assertion
        """
        if not callable(self.val):
            raise TypeError("val must be callable")
        if not issubclass(ex, BaseException):
            raise TypeError("given arg must be exception")

        # chain on with ex as the expected exception
        return self.builder(self.val, self.description, self.kind, ex, self.logger)

    def when_called_with(self, *some_args, **some_kwargs) -> Self:
        """Asserts that val, when invoked with the given args and kwargs, raises the expected exception.

        Invokes ``val()`` with the given args and kwargs.  You must first set the expected
        exception with :meth:`~raises` or :meth:`~does_not_raise`.

        Args:
            *some_args: the args to call ``val()``
            **some_kwargs: the kwargs to call ``val()``

        Examples:
            Usage::

                def some_func(a):
                    raise RuntimeError('some error!')

                assert_that(some_func).raises(RuntimeError).when_called_with('foo')

        Returns:
            AssertionBuilder: returns a new instance (now with the captured exception error message as the val) to chain to the next assertion

        Raises:
            AssertionError: if val does **not** raise the expected exception
            TypeError: if expected exception not set via :meth:`raises` or :meth:`does_not_raise`
        """
        if not self.expected:
            raise TypeError("expected exception not set, raises() or does_not_raise() must be called first")

        if getattr(self, "_not_expected", False):
            return self._when_called_with_not_expected(*some_args, **some_kwargs)

        try:
            self.val(*some_args, **some_kwargs)
        except BaseException as e:
            if issubclass(type(e), self.expected):
                return self.builder(str(e), self.description, self.kind, logger=self.logger)
            else:
                self.error(
                    f"Expected <{self.val.__name__}> to raise <{self.expected.__name__}>"
                    f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)}),"
                    f" but raised <{type(e).__name__}>."
                )
                return _InertBuilder()

        self.error(
            f"Expected <{self.val.__name__}> to raise <{self.expected.__name__}>"
            f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)})."
        )
        return _InertBuilder()

    def _when_called_with_not_expected(self, *some_args, **some_kwargs) -> Self:
        try:
            self.val(*some_args, **some_kwargs)
        except BaseException as e:
            if issubclass(type(e), self.expected):
                self.error(
                    f"Expected <{self.val.__name__}> to not raise <{self.expected.__name__}>"
                    f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)}),"
                    f" but did raise <{type(e).__name__}>."
                )
                return _InertBuilder()
        return self

    def does_not_raise(self, ex) -> Self:
        """Asserts that val is callable and sets the not-expected exception.

        Just sets the not-expected exception, but never calls val. You must
        chain to :meth:`~when_called_with` to invoke ``val()``.

        Args:
            ex: the exception that should **not** be raised

        Examples:
            Usage::

                assert_that(some_func).does_not_raise(RuntimeError).when_called_with('foo')

        Returns:
            AssertionBuilder: returns a new instance to chain to the next assertion
        """
        if not callable(self.val):
            raise TypeError("val must be callable")
        if not issubclass(ex, BaseException):
            raise TypeError("given arg must be exception")

        new_builder = self.builder(self.val, self.description, self.kind, ex, self.logger)
        new_builder._not_expected = True
        return new_builder
