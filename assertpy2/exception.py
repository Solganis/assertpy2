from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from ._mixin_base import _MixinBase

if TYPE_CHECKING:
    from ._compat import Self

__tracebackhide__ = True

_UNSET: Final = object()  # sentinel: no return value captured yet


class _InertBuilder:
    """No-op builder returned after a failed raises/when_called_with in soft mode.

    Silently absorbs all chained assertions so they don't crash on wrong val type.
    """

    def __getattr__(self, name):
        return lambda *args, **kwargs: self


class ExceptionMixin(_MixinBase):
    """Expected exception mixin."""

    def raises(self, ex: type) -> Self:
        """Asserts that val is callable and set the expected exception.

        Just sets the expected exception, but never calls val, and therefore never fails. You must
        chain to [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with] to invoke ``val()``.

        Args:
            ex: the expected exception

        Examples:
            Usage:

                assert_that(some_func).raises(RuntimeError).when_called_with('foo')

        Returns:
            AssertionBuilder: returns a new instance (with the expected exception) to chain the next assertion
        """
        if not callable(self.val):
            raise TypeError("val must be callable")
        if not issubclass(ex, BaseException):
            raise TypeError("given arg must be exception")

        return self.builder(self.val, self.description, self.kind, ex, self.logger)

    def when_called_with(self, *some_args: object, **some_kwargs: object) -> Self:
        """Asserts that val, when invoked with the given args and kwargs, meets the set expectation.

        Invokes ``val()`` with the given args and kwargs.  You must first set an expectation with
        [`raises()`][assertpy2.exception.ExceptionMixin.raises] or
        [`does_not_raise()`][assertpy2.exception.ExceptionMixin.does_not_raise] (expected exception),
        or with
        [`warns()`][assertpy2.warning.WarningMixin.warns] or
        [`does_not_warn()`][assertpy2.warning.WarningMixin.does_not_warn] (expected warning).

        Args:
            *some_args: the args to call ``val()``
            **some_kwargs: the kwargs to call ``val()``

        Examples:
            Usage:

                def some_func(a):
                    raise RuntimeError('some error!')

                assert_that(some_func).raises(RuntimeError).when_called_with('foo')

        Returns:
            AssertionBuilder: returns a new instance (now with the captured exception or warning
                message as the val) to chain to the next assertion

        Raises:
            AssertionError: if val does **not** meet the set expectation
            TypeError: if no expectation set first
        """
        if self._expected_warning is not None:
            if self._not_expected:
                return self._when_called_with_not_warning(self._expected_warning, *some_args, **some_kwargs)
            return self._when_called_with_warning(self._expected_warning, *some_args, **some_kwargs)

        if not self.expected:
            raise TypeError("no expectation set; call raises(), warns() or a does_not_* method first")

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
                return cast("Self", _InertBuilder())

        self.error(
            f"Expected <{self.val.__name__}> to raise <{self.expected.__name__}>"
            f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)})."
        )
        return cast("Self", _InertBuilder())

    def returned(self) -> Self:
        """Pivots the chain to the value ``val()`` returned during
        [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with].

        Use after a call that completed normally ([`warns()`][assertpy2.warning.WarningMixin.warns],
        [`does_not_warn()`][assertpy2.warning.WarningMixin.does_not_warn], or
        [`does_not_raise()`][assertpy2.exception.ExceptionMixin.does_not_raise]) to assert
        on the return value in the same chain.

        Examples:
            Usage:

                assert_that(make_client).warns(DeprecationWarning).when_called_with().returned().is_instance_of(Client)
                assert_that(adder).does_not_raise(TypeError).when_called_with(1, 2).returned().is_equal_to(3)

        Returns:
            AssertionBuilder: a new instance wrapping the captured return value

        Raises:
            TypeError: if no return value was captured (the call raised, or
                [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with]
                was not invoked first)
        """
        if self._return_value is _UNSET:
            raise TypeError("no return value captured; returned() is only valid after a call that completed normally")
        return self.builder(self._return_value, self.description, self.kind, logger=self.logger)

    def _when_called_with_not_expected(self, *some_args, **some_kwargs) -> Self:
        assert self.expected is not None
        try:
            result = self.val(*some_args, **some_kwargs)
        except BaseException as e:
            if issubclass(type(e), self.expected):
                self.error(
                    f"Expected <{self.val.__name__}> to not raise <{self.expected.__name__}>"
                    f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)}),"
                    f" but did raise <{type(e).__name__}>."
                )
                return cast("Self", _InertBuilder())
            return self
        self._return_value = result
        return self

    def does_not_raise(self, ex: type) -> Self:
        """Asserts that val is callable and sets the not-expected exception.

        Just sets the not-expected exception, but never calls val. You must
        chain to [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with] to invoke ``val()``.

        Args:
            ex: the exception that should **not** be raised

        Examples:
            Usage:

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
