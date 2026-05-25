# Contributing

Contributions of docs, tests, or code are welcome.

1. Fork it
1. Clone your fork (`git clone https://my_fork`)
1. Create a branch (`git checkout -b my_branch`)
1. Commit your changes (`git commit -am "added some cool feature"`)
1. Push your branch to your fork (`git push origin my_branch`)
1. Open a [Pull Request](http://github.com/Solganis/assertpy2/pulls)
1. Respond to any questions during our review process

Read more about how pulls work on GitHub's [About pull requests](https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/about-pull-requests) page.

## Running the Tests

Before sending a pull request, write tests (and use `assertpy2` assertions in them).

```
uv sync
uv run pytest -v
```
