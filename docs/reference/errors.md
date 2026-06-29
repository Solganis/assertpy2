# Structured failures

The exception raised when an assertion fails, plus the structured diff it carries. ``AssertionFailure``
subclasses ``AssertionError``, so existing ``except AssertionError`` handlers keep working. See
[Errors & reporting](../errors.md) for usage.

::: assertpy2.errors.AssertionFailure
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy2.errors.DiffResult
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy2.errors.DiffEntry
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true
