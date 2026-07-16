# Structured failures

The exception raised when an assertion fails, carrying the structured diff.

``AssertionFailure`` subclasses ``AssertionError``, so existing ``except AssertionError`` handlers keep
working unchanged. See [Errors & reporting](../guides/errors.md) for usage.

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

::: assertpy2.errors.PollTrace
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy2.errors.PollSample
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true
