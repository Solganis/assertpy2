from __future__ import annotations

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Enrich failure reports when an AssertionError carries structured data.

    Uses duck typing (``getattr``) to detect ``actual``/``expected``/``diff``
    attributes so that ``assertpy2`` itself is never imported at plugin-load
    time.  This keeps pytest-cov's coverage tracking accurate.
    """
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return
    if call.excinfo is None:
        return

    exc = call.excinfo.value
    if not isinstance(exc, AssertionError):
        return

    actual = getattr(exc, "actual", None)
    expected = getattr(exc, "expected", None)
    diff = getattr(exc, "diff", None)

    if actual is None and expected is None and diff is None:
        return

    if actual is not None or expected is not None:
        lines = []
        if actual is not None:
            lines.append("  actual:   %r" % (actual,))
        if expected is not None:
            lines.append("  expected: %r" % (expected,))
        report.sections.append(("AssertionFailure", "\n".join(lines)))

    if diff is not None:
        report.sections.append(("Structured Diff", str(diff)))
