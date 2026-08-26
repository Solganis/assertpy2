from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..errors import AssertionFailure, DiffResult, PollTrace
    from ..http_mixin import _Response
    from ..outcome import AssertionOutcome
    from ._compare import _CompareConfig
    from ._compat import Self
    from ._introspection import WarningLogger


class _MixinBase:
    _response: _Response | None = None
    """The HTTP response this value came from, when it came from one.

    Carried by every pivot rather than looked up at the end, because the response is gone by the time a
    failure is composed over its parsed body.
    """

    _equality_comparison = False
    """Whether the failure being reported came from asking whether two values are equal.

    Read by the failure composer.  Only there does it follow from a type comparing by identity that
    nothing on the other side could have passed: a containment failure over the same values is about
    where they sit, and a comparator of the caller's own owns its leaves outright.
    """

    if TYPE_CHECKING:
        val: Any
        description: str
        kind: str | None
        expected: type[BaseException] | None
        logger: WarningLogger
        _not_expected: bool
        _expected_warning: type[Warning] | None
        _return_value: object
        _raised_exception: object

        def error(
            self,
            msg: str,
            *,
            actual: object = ...,
            expected: object = ...,
            diff: DiffResult | None = ...,
            suppress_context: bool = ...,
        ) -> Self: ...

        def _compose(
            self,
            msg: str,
            *,
            actual: object,
            expected: object,
            diff: DiffResult | None,
            trace: PollTrace | None,
        ) -> AssertionOutcome: ...

        @staticmethod
        def _failure(outcome: AssertionOutcome) -> AssertionFailure: ...

        def builder(
            self,
            val: object,
            description: str = ...,
            kind: str | None = ...,
            expected: type[BaseException] | None = ...,
            logger: WarningLogger | None = ...,
            origin: str | None = ...,
        ) -> Self: ...

        def _when_called_with_warning(
            self, expected: type[Warning], *some_args: object, **some_kwargs: object
        ) -> Self: ...

        def _when_called_with_not_warning(
            self, expected: type[Warning], *some_args: object, **some_kwargs: object
        ) -> Self: ...

        def _fmt_items(self, items: object) -> str: ...

        def _fmt_args_kwargs(self, *some_args: object, **some_kwargs: object) -> str: ...

        def _validate_between_args(self, val_type: type, low: object, high: object) -> None: ...

        def _validate_close_to_args(self, val: object, other: object, tolerance: object) -> None: ...

        def _is_dict_like(
            self,
            candidate: object,
            check_keys: bool = ...,
            check_values: bool = ...,
            check_getitem: bool = ...,
        ) -> bool: ...

        def _require_dict_like(
            self,
            candidate: object,
            check_keys: bool = ...,
            check_values: bool = ...,
            check_getitem: bool = ...,
            name: str = ...,
        ) -> None: ...

        def _check_iterable(self, val: object, check_getitem: bool = ..., name: str = ...) -> None: ...

        def _dict_not_equal(
            self,
            val: object,
            other: object,
            ignore: object = ...,
            include: object = ...,
            config: _CompareConfig | None = ...,
        ) -> bool: ...

        def _dict_err(
            self,
            val: object,
            other: object,
            ignore: object = ...,
            include: object = ...,
            config: _CompareConfig | None = ...,
        ) -> None: ...

        @staticmethod
        def _to_comparable_dict(obj: object) -> dict[str, object] | None: ...

        _NUMERIC_COMPAREABLE: frozenset[type]
        _NUMERIC_NON_COMPAREABLE: frozenset[type]

        def contains(self, *items: object) -> Self: ...

        def does_not_contain(self, *items: object) -> Self: ...

        # `Any`, not `object`: the real one is annotated per value type, and a wider declaration here would be an
        # incompatible override
        def starts_with(self, prefix: Any) -> Self: ...

        def is_equal_to(self, other: object, **kwargs: object) -> Self: ...

        def is_not_equal_to(self, other: object) -> Self: ...
