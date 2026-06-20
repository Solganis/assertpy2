from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._compat import Self
    from .errors import DiffResult


class _MixinBase:
    if TYPE_CHECKING:
        val: Any
        description: str
        kind: str | None
        expected: type[BaseException] | None
        logger: logging.LoggerAdapter
        _not_expected: bool
        _expected_warning: type[Warning] | None

        def error(
            self,
            msg: str,
            *,
            actual: object = ...,
            expected: object = ...,
            diff: DiffResult | None = ...,
        ) -> Self: ...

        def builder(
            self,
            val: object,
            description: str = ...,
            kind: str | None = ...,
            expected: BaseException | None = ...,
            logger: logging.LoggerAdapter | None = ...,
        ) -> Self: ...

        # WarningMixin (terminals dispatched from ExceptionMixin.when_called_with)

        def _when_called_with_warning(
            self, expected: type[Warning], *some_args: object, **some_kwargs: object
        ) -> Self: ...

        def _when_called_with_not_warning(
            self, expected: type[Warning], *some_args: object, **some_kwargs: object
        ) -> Self: ...

        # HelpersMixin

        def _fmt_items(self, items: object) -> str: ...

        def _fmt_args_kwargs(self, *some_args: object, **some_kwargs: object) -> str: ...

        def _validate_between_args(self, val_type: type, low: object, high: object) -> None: ...

        def _validate_close_to_args(self, val: object, other: object, tolerance: object) -> None: ...

        def _check_dict_like(
            self,
            d: object,
            check_keys: bool = ...,
            check_values: bool = ...,
            check_getitem: bool = ...,
            name: str = ...,
            return_as_bool: bool = ...,
        ) -> bool | None: ...

        def _check_iterable(self, val: object, check_getitem: bool = ..., name: str = ...) -> None: ...

        def _dict_not_equal(
            self,
            val: object,
            other: object,
            ignore: object = ...,
            include: object = ...,
        ) -> bool: ...

        def _dict_err(
            self,
            val: object,
            other: object,
            ignore: object = ...,
            include: object = ...,
        ) -> None: ...

        @staticmethod
        def _to_comparable_dict(obj: object) -> dict[str, object] | None: ...

        # NumericMixin class attrs used by HelpersMixin._validate_between_args
        _NUMERIC_COMPAREABLE: frozenset[type]
        _NUMERIC_NON_COMPAREABLE: frozenset[type]

        # Cross-mixin methods

        def contains(self, *items: object) -> Self: ...

        def does_not_contain(self, *items: object) -> Self: ...

        def is_equal_to(self, other: object, **kwargs: object) -> Self: ...

        def is_not_equal_to(self, other: object) -> Self: ...
