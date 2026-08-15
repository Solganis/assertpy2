# Consumer corpus

Small projects that use this library the way somebody else's suite does, checked against an installed
build rather than against the source tree.

## Why it exists

The suite in `tests/` proves the library behaves. It cannot prove that the *typed surface* fits code
nobody here wrote, and that is where the last several defects came from: a selector type that refused a
mapping with its own `__getitem__`, a `slice` that stopped type-checking on Python 3.10, a predicate
parameter that lost the element type. Each was found by guessing at somebody else's code. A corpus finds
them by running it.

It also answers a question the suite structurally cannot: does the package **install** and work from a
wheel and from an sdist, with only the extras a consumer actually asked for.

## What is checked

For every project, against an installed `assertpy2`:

- the project's own tests pass;
- mypy, pyright and ty all accept the project's code;
- no optional dependency is present that the project did not ask for, so an import that should be
  optional cannot become mandatory unnoticed.

## Running it

    python corpus/run.py                      # every project, installed from a wheel
    python corpus/run.py --from sdist         # the same, installed from an sdist
    python corpus/run.py --only pytest_style  # one project
    python corpus/run.py --checkers mypy      # one checker
    python corpus/run.py --keep               # leave the environments behind to poke at

Each project gets its own environment, built fresh, so a dependency in one cannot mask a missing
dependency in another. `--keep` leaves them under `corpus/.envs`; otherwise they are removed as each
project finishes.

In CI it runs on a schedule, on demand, and on any change to the typed surface or the packaging, across
both ends of the supported Python range and both install formats. Not in the main gate: it builds the
package and creates an environment per project, so it takes minutes.

## What it has already found

- `Matcher` written without a type argument, which made every member carrying it "partially unknown"
  under pyright in strict mode: a typed consumer could not use the library without errors.

## Adding a project

A directory under `corpus/projects/` with a `corpus.toml` saying what to install and what to run, plus
the code itself. Nothing else is wired by hand: `run.py` discovers directories.

The point of a new project is a *shape of consumer code we do not already exercise*, not more assertions.
Before adding one, say which shape it brings.
