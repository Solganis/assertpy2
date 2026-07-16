# Overview

This reference is generated from the source docstrings and is grouped by the **mixin that implements
each assertion**, mirroring the code layout.

The assertions actually available on a value are the **union of the mixins for its type**. On a string
(``assert_that("x")``), for example, that is everything on [String assertions](strings.md),
[Containment assertions](containment.md), [Core & objects](core.md), and
[File & path assertions](files.md).

For a task-oriented view organized by value type instead, see the
[Type assertions guide](../guides/assertions.md).

- [Entry points](entry-points.md) - the top-level functions such as ``assert_that``, ``assert_conforms``,
  ``assert_warn``, ``soft_assertions``, and ``fail``.
- [Matchers](matchers.md) - the ``match.*`` namespace of composable matchers.
- [Core & objects](core.md) - assertions available on every value (equality, identity, ``satisfies``, ...).
- Type-specific pages - strings, numbers, collections, dicts, dates, files, bytes.
- [Dynamic assertions](dynamic.md) - the ``has_<name>()`` family.
- [Exception & callable assertions](exceptions.md) - ``raises()``, ``caused_by()``, ``contains_error()``, ``raised()``.
- [Extracting](extracting.md), [JSON assertions](json.md), [Data frame & array assertions](dataframes.md), and [Snapshot assertions](snapshots.md).
- [Structured failures](errors.md), [Warning assertions](warnings.md), and [Async & eventual assertions](async.md).

Signatures here are the runtime implementations. How the static return type narrows per value type (the
typed overloads that drive editor autocomplete) is explained in [Type safety](../concepts/type-safety.md).
