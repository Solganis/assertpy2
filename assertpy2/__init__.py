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
from .file import contents_of

__all__ = [
    "WarningLoggingAdapter",
    "__version__",
    "add_extension",
    "assert_that",
    "assert_warn",
    "contents_of",
    "fail",
    "remove_extension",
    "soft_assertions",
    "soft_fail",
]
