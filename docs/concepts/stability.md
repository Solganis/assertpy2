# Stability

What you can build on, and what enforces it. Every row below is held by a test that fails CI, not by
an intention.

## The contract

| You can depend on | Enforced by |
|---|---|
| The 37 names `assertpy2` exports, and the fields of every record it hands you | [`test_public_surface.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_public_surface.py) pins both against a hand-written list |
| Every assertion the type checker offers you existing at runtime | [`test_protocol_parity.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_protocol_parity.py) walks all twelve protocols |
| The type your chain has after each step | [`test_typing.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_typing.py), 126 `assert_type` checks under ty, mypy `--strict` and Pyright, zero suppressions |
| One relation keeping one name across the API | [`test_api_vocabulary.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_api_vocabulary.py) |
| The three-method `Matcher` protocol your custom matchers implement | [`test_matcher_parity.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_matcher_parity.py) |
| The Allure attachment schema | versioned in its own `format` field, so a consumer branches on a number rather than guessing |
| Your assertions keeping their verdict | the suite at 100 % branch coverage, plus mutation testing |

The records in the first row are `AssertionOutcome`, `MatchResult`, `DiffEntry`, `DiffResult`, `Step`,
`PollSample` and `PollTrace`. Fields are added, never renamed or removed, inside a major version.

Documentation is held to the same bar: every example in these guides is executed and type-checked in
CI, so a snippet you copy is one that ran.

## Reading a failure from code

Failures carry [structured data](../guides/errors.md#structured-errors) for exactly this. Reach for it
rather than for the rendered text:

| You want | Use |
|---|---|
| the values that were compared | `failure.actual`, `failure.expected` |
| where they differ | `failure.diff.entries`, each with a `path` |
| a location you can walk in code | [`entry.steps`](../guides/errors.md#paths-a-program-can-follow) |
| every failure a soft block collected | `failure.failures` |
| a verdict without an exception | [`check()`](../guides/errors.md#asking-instead-of-asserting) |

Those are covered by the table above. **Message wording is not**: it improves in minor releases, so a
`pytest.raises(match=...)` written against our phrasing, or a snapshot of a failing run, is the one
thing that predictably needs updating. Match on the exception type and read the fields.

## Upgrading

Semantic versioning, read strictly: a new assertion is a minor, a patch carries fixes only.

Two kinds of change ship in a minor, and the release notes list each one under **Behaviour changes**:

- **an input that was silently wrong starts raising**, such as an empty prefix that no value could fail
- **a wrong verdict is corrected**, so an assertion that passed and should not have begins to fail

Both are the reason to read that section before upgrading. Nothing else in a minor is designed to
change what your suite reports.

## Not part of the API

Anything whose name starts with `_`, and the module an assertion happens to live in. The reference
lists `matches_structure()` because you can call it from `assert_that()`, and its anchor reads
`assertpy2._satisfies.SatisfiesMixin.matches_structure` because that is where the code sits.
Importing from there is not supported.

Python 3.10 and up. Dropping a version that upstream still supports would be a major.

Code written against [assertpy](../getting-started/migration.md) keeps working, and that holds for
refactors: an internal change that would break a documented assertpy call is not internal.
