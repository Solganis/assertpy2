# Stability

What you can build on, and what enforces it. Every row below is held by a test that fails CI, not by
an intention.

## The contract

| You can depend on | Enforced by |
|---|---|
| The 37 names `assertpy2` exports, and the fields of every record it hands you | [`test_public_surface.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_public_surface.py) pins both against a hand-written list |
| Every assertion the type checker offers you existing at runtime | [`test_protocol_parity.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_protocol_parity.py) walks all twenty-nine protocols |
| The signature you call: parameter names, their order, their defaults | [`test_api_compatibility.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_api_compatibility.py) compares a recorded snapshot of the whole surface and classifies every change as breaking, an addition, or typing-only |
| The type your chain has after each step | [`test_typing.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_typing.py), 207 `assert_type` checks under ty, mypy `--strict`, Pyright and Pyrefly, zero suppressions |
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

Those fields are covered by the table above.

**Message wording is not.** It improves in minor releases, so a `pytest.raises(match=...)` written
against our phrasing, or a snapshot of a failing run, is the one thing that predictably needs updating.
Match on the exception type and read the fields.

Where the promise ends, so the edges are decided rather than assumed:

- `AssertionFailure` is an `AssertionError`, and stays one. An existing `except AssertionError` keeps
  working.
- On a failure raised by this library, `actual`, `expected`, `diff`, `trace` and `failures` are there to
  read. `trace` is set for polling assertions, `failures` for a soft block, and both are `None` and empty
  elsewhere.
- `has_expected` says whether an expectation was named at all, which `expected is None` cannot. It
  does not separate `is_equal_to(None)` from `is_none()`, and is not meant to: both compare against
  `None`, so both named one.
- Nothing public says whether the *actual* side was named.
- Constructing `AssertionFailure` yourself is not part of the API. Raise your own `AssertionError`, or
  let an assertion raise this one.

## Upgrading

Semantic versioning, read strictly: a new assertion is a minor, a patch carries fixes only.

Five kinds of change ship in a minor, and the release notes list each one under **Behaviour changes**:

- **an input that was silently wrong starts raising**, such as an empty prefix that no value could fail
- **a wrong verdict is corrected**, so an assertion that passed and should not have begins to fail
- **a diagnostic that was wrong is corrected**, so a failure says something different while failing for
  the same reason
- **a type stops offering what the value cannot answer**, so a call that type-checked and then raised
  becomes a type error instead
- **a report that was opt-in becomes default**, so a run prints something it did not print before while
  every verdict stays where it was. Its setting still turns it off

Nothing else in a minor is designed to change what your suite reports, which is why that section is
the one to read before upgrading.

The third kind moves no verdict. A count that described more than it had measured is the usual case,
and the fix moves the number rather than the pass or fail. What it does move is a test matching the old
text with `pytest.raises(match=...)`.

The fourth is the half worth planning for. Runtime does not change and your tests keep passing, but a
CI stage running mypy, Pyright or ty can go red before them. Every narrowed chain is named in the
release notes, and these are the ones so far:

| The chain | What it stopped offering |
|---|---|
| the invoked view | the filesystem assertions, since the text of an exception is not a filename |
| `at_json_path()` | a shape it cannot know, answering with the core assertions instead |
| `extracting()` | its first selector as optional or by keyword, since `extracting(name="user")` never ran |
| a predicate parameter | an unnamed element, now naming the one it is handed |
| a `datetime.date` value | the nine assertions that read a time of day, which always raised on a plain date. A `datetime` keeps every one |
| a value the library cannot use | the assertions it could never answer |

The last row is the widest so far, so it is worth saying plainly which values it touches:

| | |
|---|---|
| **unaffected** | a value with a type this library knows, and anything typed `Any`, which is what an unannotated helper or a `json.loads()` result gives you |
| **narrowed** | a value annotated `object`, and a class answering to nothing the library can use: no length, no iteration, no mapping, not a model, not a response |

Narrowed values get the assertions every value can answer rather than the whole surface, so
`assert_that(person).is_positive()` is a type error instead of a runtime one. Dynamic
`has_<attribute>()` narrows with them, since the hook it resolves through lives on the full builder.

Runtime is unchanged in every case. The migration is to assert on the attribute rather than through
it, as `assert_that(person.name).is_equal_to("Fred")`.

### Which release a typing change ships in

The fourth kind above is the one that needs its own reading, because a typing change and a runtime
change are not the same size even when they touch the same method. Three categories, and the test is
what a caller has to do about it.

- **Patch** for an annotation that was simply wrong, where no correct call changes meaning. A parameter
  that always accepted a `float` and said `int` is one of these: nothing you wrote stops working, and
  something you could not write starts.
- **Minor** for a tightening with a migration, which is where almost all of them land. The runtime does
  not change, your suite goes on passing, and a type-check stage can go red before it. Taking dynamic
  `has_<attribute>()` off a plain class is one: the call still runs, and the migration is to assert on
  the attribute rather than through it.
- **Major** for removing or changing a documented typed API with no equivalent to move to. A renamed
  method, a return type that is not a refinement of the old one, a capability that simply goes.

Every typing change in a minor is named in the release notes with the call that stops type-checking,
the reason, and what to write instead.

What is mechanised is the *noticing*, not the category. The API snapshot in `tests/api_surface.py`
records what each typed view offers and how it takes its parameters, both resolved through the bases
rather than read where they are written. A name leaving a view is classified as `typing`, and so is a
parameter turning keyword-only, whether that happened where it was declared or by an override further
down.

Which of the three categories a change belongs to is a judgement made in review. The snapshot does not
make it.

## Not part of the API

Anything whose name starts with `_`, and the module an assertion happens to live in. The reference
lists `matches_structure()` because you can call it from `assert_that()`, and its anchor reads
`assertpy2._satisfies.SatisfiesMixin.matches_structure` because that is where the code sits.
Importing from there is not supported.

Python 3.10 and up. Dropping a version that upstream still supports would be a major.

Code written against [assertpy](../getting-started/migration.md) keeps working, and that holds for
refactors: an internal change that would break a documented assertpy call is not internal.
