# Contributing

Contributions of docs, tests, or code are welcome.

## Workflow

1. Fork the repo
2. Clone your fork (`git clone <your_fork_url>`)
3. Create a branch (`git checkout -b my_branch`)
4. Install dependencies: `uv sync`
5. Make your changes
6. Run the [verification pipeline](#verification-pipeline) and fix any issues
7. Commit using [Conventional Commits](#commit-style)
8. Push your branch (`git push origin my_branch`)
9. Open a [Pull Request](http://github.com/Solganis/assertpy2/pulls)

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
