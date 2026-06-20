from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, cast

from ._mixin_base import _MixinBase
from .exception import _InertBuilder

if TYPE_CHECKING:
    from ._compat import Self

__tracebackhide__ = True


class WarningMixin(_MixinBase):
    """Expected warning mixin (a ``pytest.warns``-style assertion).

    The front verbs (:meth:`warns` / :meth:`does_not_warn`) only record the expected warning
    category; the actual invocation happens in
    :meth:`~assertpy2.exception.ExceptionMixin.when_called_with`, which dispatches to the private
    handlers below.
    """

    def warns(self, warning: type[Warning] = Warning) -> Self:
        """Asserts that val is callable and sets the expected warning category.

        Just records the expectation, but never calls val.  You must chain to
        :meth:`~assertpy2.exception.ExceptionMixin.when_called_with` to invoke ``val()`` inside a
        warning-capturing context.  On success, the matched warning's message becomes the new val so
        you can chain further assertions on it.

        Subclasses of the given category match, and the category defaults to the base :class:`Warning`
        (which matches any warning).

        Args:
            warning: the expected warning category (a :class:`Warning` subclass)

        Examples:
            Usage::

                assert_that(deprecated_func).warns(DeprecationWarning).when_called_with("foo")
                assert_that(deprecated_func).warns(DeprecationWarning).when_called_with("foo").matches("since 2.6")

        Returns:
            AssertionBuilder: returns a new instance (now with the expected warning) to chain to
                :meth:`~assertpy2.exception.ExceptionMixin.when_called_with`

        Note:
            Capturing warnings mutates process-global state, so this is **not** thread-safe across OS
            threads (the same caveat as ``pytest.warns``).  It is safe within a single thread,
            including multiple ``asyncio`` tasks on one event loop.
        """
        return self._warning_builder(warning)

    def does_not_warn(self, warning: type[Warning] = Warning) -> Self:
        """Asserts that val is callable and sets the not-expected warning category.

        Just records the expectation, but never calls val.  You must chain to
        :meth:`~assertpy2.exception.ExceptionMixin.when_called_with` to invoke ``val()`` and assert
        that no warning of the given category is emitted.  The category defaults to the base
        :class:`Warning` (which forbids any warning).

        Args:
            warning: the warning category that should **not** be emitted (a :class:`Warning` subclass)

        Examples:
            Usage::

                assert_that(safe_func).does_not_warn(DeprecationWarning).when_called_with("foo")

        Returns:
            AssertionBuilder: returns a new instance to chain to
                :meth:`~assertpy2.exception.ExceptionMixin.when_called_with`
        """
        new_builder = self._warning_builder(warning)
        new_builder._not_expected = True
        return new_builder

    def _warning_builder(self, warning: type[Warning]) -> Self:
        """Validate args and build a new instance carrying the expected warning category."""
        if not callable(self.val):
            raise TypeError("val must be callable")
        if not issubclass(warning, Warning):
            raise TypeError("given arg must be a warning")
        new_builder = self.builder(self.val, self.description, self.kind, logger=self.logger)
        new_builder._expected_warning = warning
        return new_builder

    def _when_called_with_warning(self, expected: type[Warning], *some_args, **some_kwargs) -> Self:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")  # bypass __warningregistry__ "show once" dedup and filterwarnings=error
            self.val(*some_args, **some_kwargs)
        matched = [w for w in caught if issubclass(w.category, expected)]
        if matched:
            return self.builder(str(matched[0].message), self.description, self.kind, logger=self.logger)
        if caught:
            seen = ", ".join(sorted({w.category.__name__ for w in caught}))
            self.error(
                f"Expected <{self.val.__name__}> to warn <{expected.__name__}>"
                f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)}),"
                f" but warned <{seen}>."
            )
            return cast("Self", _InertBuilder())
        self.error(
            f"Expected <{self.val.__name__}> to warn <{expected.__name__}>"
            f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)})."
        )
        return cast("Self", _InertBuilder())

    def _when_called_with_not_warning(self, expected: type[Warning], *some_args, **some_kwargs) -> Self:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")  # bypass __warningregistry__ "show once" dedup and filterwarnings=error
            self.val(*some_args, **some_kwargs)
        matched = [w for w in caught if issubclass(w.category, expected)]
        if matched:
            seen = ", ".join(sorted({w.category.__name__ for w in matched}))
            self.error(
                f"Expected <{self.val.__name__}> to not warn <{expected.__name__}>"
                f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)}),"
                f" but did warn <{seen}>."
            )
            return cast("Self", _InertBuilder())
        return self
