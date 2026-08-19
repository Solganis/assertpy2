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

Install exactly this set. A bare `uv sync` leaves out the optional libraries several tests import, and
those tests fail rather than skip:

```bash
uv sync --extra json --extra data --extra inline --group integrations --group docs-examples
```

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check assertpy2/ tests/test_typing.py
uv run pytest --cov=assertpy2 --cov-fail-under=100 --ignore=tests/test_docs_examples.py tests
uv run pytest tests/test_docs_examples.py tests/test_typing_claims.py
uv run --group docs mkdocs build --strict
```

The public typing surface is checked by three checkers. Run them after the block above, not before:
`uv run --group typecheck` adds the checkers to the same `.venv` and leaves them there, and a coverage
run with them installed collects a different set:

```bash
uv run --group typecheck mypy --strict --follow-imports=silent tests/test_typing.py
uv run --group typecheck pyright tests/test_typing.py
uv run --group typecheck pytest tests/test_pyright_baseline.py
```

Three details that cost time if you meet them the hard way:

- `ty check` is scoped on purpose. Run over the whole tree it reports hundreds of diagnostics from
  `tests/`, which is full of deliberate negative typing cases: calls that must not type-check.
- `--all-extras` is not a shortcut for the sync line. Installing `allure` or `behave` makes 100%
  coverage unreachable by construction, because the `except ImportError` branch guarding them stops
  being executed. CI never installs them for the coverage job either.
- `tests/test_docs_examples.py` is run separately because it executes the snippets in `docs/`, which
  needs the `docs-examples` group and a different collection.

CI requires 100% code coverage.

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
