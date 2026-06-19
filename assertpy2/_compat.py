"""Internal compatibility shims.

``Self`` entered the standard library's :mod:`typing` in Python 3.11; on 3.10 it is provided by
``typing_extensions``. Re-exporting it from one place lets every mixin import ``Self`` without repeating
the version gate, and lets ``typing_extensions`` be dropped as a runtime dependency on Python 3.11+.
"""

import sys

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

__all__ = ["Self"]
