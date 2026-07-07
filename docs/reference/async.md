# Async & eventual assertions

Poll a callable until an assertion passes or the timeout expires. Start with ``eventually()`` on a
callable value, chain the assertion you expect to eventually hold, and await the result - or use
``eventually_sync()`` for the same polling without an event loop. See
[Testing](../testing.md#async-assertions) for usage.

::: assertpy2.assertpy.AssertionBuilder.eventually
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy2.assertpy.AssertionBuilder.eventually_sync
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy2.async_assertions.AsyncAssertionBuilder

::: assertpy2.async_assertions.SyncAssertionBuilder
