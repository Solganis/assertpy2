# Contributing

Contributions of docs, tests, or code are welcome.

## Workflow

1. For a new assertion or matcher, open an issue first. The API grows from demand, and a working
   implementation on its own is not enough to land one
2. Fork the repo
3. Clone your fork (`git clone <your_fork_url>`)
4. Create a branch (`git checkout -b my_branch`)
5. Install dependencies: `uv sync`
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

```bash
# lint
uv run ruff check assertpy2/ tests/

# format
uv run ruff format --check assertpy2/ tests/

# type check
uv run ty check

# tests with coverage (must be 100%)
uv run pytest tests/ -v --cov=assertpy2 --cov-report=term-missing
```

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
