from .assertpy import (
    WarningLoggingAdapter,
    __version__,
    add_extension,
    assert_that,
    assert_warn,
    fail,
    remove_extension,
    soft_assertions,
    soft_fail,
)
from .async_assertions import AsyncAssertionBuilder
from .errors import AssertionFailure, DiffEntry, DiffResult
from .file import contents_of
from .matchers import Matcher, match, register_matcher, unregister_matcher

__all__ = [
    "AssertionFailure",
    "AsyncAssertionBuilder",
    "DiffEntry",
    "DiffResult",
    "Matcher",
    "WarningLoggingAdapter",
    "__version__",
    "add_extension",
    "assert_that",
    "assert_warn",
    "contents_of",
    "fail",
    "match",
    "register_matcher",
    "remove_extension",
    "soft_assertions",
    "soft_fail",
    "unregister_matcher",
]
