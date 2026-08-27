# Contributing

Contributions of docs, tests, or code are welcome.

## Workflow

1. For a new assertion or matcher, open an issue first. The API grows from demand, and a working
   implementation on its own is not enough to land one
2. Fork the repo
3. Clone your fork (`git clone <your_fork_url>`)
4. Create a branch (`git checkout -b my_branch`)
5. Install dependencies with the [one sync command](#verification-pipeline) below, not a bare `uv sync`
6. Make your changes
7. Run the [verification pipeline](#verification-pipeline) and fix any issues
8. Commit using [Conventional Commits](#commit-style)
9. Push your branch (`git push origin my_branch`)
10. Open a [Pull Request](http://github.com/Solganis/assertpy2/pulls)

Read more about how pulls work on GitHub's [About pull requests](https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/about-pull-requests) page.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) as the package manager

## Verification pipeline

Run all checks before submitting a PR. Every step must pass.

### Install

A bare `uv sync` leaves out the optional libraries several tests import, and those tests then fail
rather than skip. Install exactly this set:

```bash
uv sync --extra json --extra data --extra inline --group integrations --group docs-examples
```

### The main gate

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check assertpy2/ tests/test_typing.py
uv run pytest --cov=assertpy2 --cov-fail-under=100 --ignore=tests/test_docs_examples.py tests
uv run pytest tests/test_docs_examples.py tests/test_typing_claims.py
uv run --group docs mkdocs build --strict
```

CI requires 100% code coverage.

### Then once on the supported floor

Run the suite on Python 3.10 as well. This is not optional, and the block above does not cover it.

A union carries `__name__` from 3.14 onwards and not before. `logging.LoggerAdapter` became
subscriptable in 3.11. Neither difference is visible to a type checker told to target 3.10, and both
shipped as defects that every other gate passed.

Use a throwaway environment. `uv run --python 3.10` inside the project rebuilds `.venv` for that
version, and on Windows it can fail partway and leave you without pytest:

```bash
uv venv /tmp/py310 --python 3.10

export VIRTUAL_ENV=/tmp/py310
uv pip install -e ".[json,data,inline]"
uv pip install pytest pytest-cov hypothesis ruff
uv pip install attrs pydantic requests httpx flask

/tmp/py310/bin/python -m pytest tests --ignore=tests/test_docs_examples.py -q
```

`ruff` belongs in that list: the tests that compare a generated file against its generator shell out
to it, and without it they fail for a reason that has nothing to do with your change.

### The four type checkers

Run these after the main gate, not before. `uv run --group typecheck` adds the checkers to the same
`.venv` and leaves them there, and a coverage run with them installed collects a different set:

```bash
uv run --group typecheck mypy --strict --follow-imports=silent tests/test_typing.py
PYRIGHT_PYTHON_FORCE_VERSION=1.1.413 uv run --group typecheck pyright --pythonversion 3.14 tests/test_typing.py
uv run --group typecheck pyrefly check tests/test_typing.py
uv run --group typecheck pytest tests/test_pyright_baseline.py
```

`PYRIGHT_PYTHON_FORCE_VERSION` picks the engine rather than the launcher. The `pyright` distribution on
PyPI stopped at 1.1.411 on 25 June, npm has shipped 1.1.412 and 1.1.413 since, and the newer one is the
first that resolves `TypeForm`. The gates that call pyright from Python pin the same build themselves,
in `tests/typing_harness.py`, so only this direct invocation needs the variable.

`--pythonversion 3.14` is not decoration. Pyright reports against the interpreter it finds unless
told otherwise, and the count moves with it: 108 diagnostics for this package on 3.10 against 102 on
3.14.

Without it a contributor on the supported floor meets a red baseline that says nothing about their
change. The baseline test passes the same target itself, so it gives one answer everywhere.

### Three details that cost time if you meet them the hard way

- `ty check` is scoped on purpose. Run over the whole tree it reports hundreds of diagnostics from
  `tests/`, which is full of deliberate negative typing cases: calls that must not type-check.
- `--all-extras` is not a shortcut for the sync line. Installing `allure` or `behave` makes 100%
  coverage unreachable by construction, because the `except ImportError` branch guarding them stops
  being executed. CI never installs them for the coverage job either.
- `tests/test_docs_examples.py` is run separately because it executes the snippets in `docs/`, which
  needs the `docs-examples` group and a different collection.

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, etc.

## Tests

Write tests for every new feature or bug fix. Use `assertpy2` assertions in tests.

## Documentation examples

Guide code blocks are executed and type-checked in CI, so an example you add has to run. A block that
cannot (pseudo-context, a deliberate failure, a rejected counter-example) is marked with an HTML comment
above the fence: `tests/test_docs_examples.py` lists the markers and what each one exempts.

Setup a page assumes (a domain class, a repository, an HTTP response) goes in
`tests/docs_fixtures.py`, not into an extra block on the page.
