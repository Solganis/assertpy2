# assertpy2

Fluent assertion library for Python. Fork of assertpy с type safety, soft assertions, snapshot testing.
Python 3.10+, единственная зависимость: typing_extensions>=4.0.

---

## Project layout

```
assertpy2/
├── assertpy.py           # assert_that(), AssertionBuilder, soft_assertions(), fail()
├── async_assertions.py   # AsyncAssertionBuilder - eventually() polling
├── base.py               # BaseMixin - is_equal_to, satisfies, each, matches_structure
├── string.py             # StringMixin - starts_with, ends_with, matches, is_alpha, is_digit
├── numeric.py            # NumericMixin - is_zero, is_positive, is_between, is_close_to
├── collection.py         # CollectionMixin - is_iterable, is_subset_of, is_sorted
├── contains.py           # ContainsMixin - contains, does_not_contain, is_empty
├── dict.py               # DictMixin - contains_key, contains_value, contains_entry
├── date.py               # DateMixin - is_before, is_after, is_equal_to_ignoring_time
├── file.py               # FileMixin + contents_of() - exists, is_file, is_directory
├── exception.py          # ExceptionMixin - raises, when_called_with
├── extracting.py         # ExtractingMixin - extracting with filter/sort
├── dynamic.py            # DynamicMixin - has_<attr>() via __getattr__
├── snapshot.py           # SnapshotMixin - snapshot testing
├── helpers.py            # HelpersMixin - _dict_not_equal, _fmt_items, validation
├── errors.py             # AssertionFailure, DiffResult, DiffEntry - structured errors
├── matchers.py           # Matcher protocol, composable matchers, match namespace
├── pytest_plugin.py      # pytest entry point - rich diff output for AssertionFailure
├── _typing.py            # TYPE_CHECKING-only Protocol classes for @overload return types
├── __init__.py           # Public API exports
└── py.typed              # PEP 561 marker

tests/                 # 100% coverage required
```

---

## Architecture

- AssertionBuilder наследует миксины. Каждый миксин - одна категория assertions.
- Все assertion-методы возвращают Self для chaining.
- error() в AssertionBuilder маршрутизирует: raise (default), log (warn), collect (soft).
- __tracebackhide__ = True во всех миксинах для чистого pytest traceback.
- Расширения через add_extension(func) - динамическая привязка через types.MethodType.

Правило: новые assertions добавляются в существующий миксин по категории.
Новый миксин создаётся только для принципиально новой категории (не для 1-2 методов).

---

## Tooling

```
uv sync
uv run pytest
uv run pytest -v --cov=assertpy2 --cov-report=term-missing
uv run ruff check .
uv run ruff format .
uv run ruff format --check .
```

---

## CI/CD

GitHub Actions, два workflow:

**CI** (.github/workflows/ci.yml):
- Триггер: push/PR в main
- Матрица: Python 3.10-3.15
- Шаги: uv sync, ruff check, pytest с coverage (xml + term-missing)
- Codecov upload: только с Python 3.14 (token в secrets)
- Отдельный lint job: ruff check + ruff format --check

**Publish** (.github/workflows/publish.yml):
- Триггер: GitHub Release (published)
- Trusted Publisher (id-token: write), без API-ключей
- uv build, pypa/gh-action-pypi-publish

Правила:
- Версия только в pyproject.toml (одно место)
- Релиз: обновить version в pyproject.toml, создать GitHub Release с тегом
- Не мержить без зелёного CI

---

## Key dependencies

| Package | Version | Role |
|---|---|---|
| typing_extensions | >=4.0 | Self type, runtime-free typing |
| pytest | >=9.0.3 | test runner (dev) |
| pytest-cov | >=6.1 | coverage (dev) |
| ruff | >=0.15.14 | linter + formatter (dev) |

---

## Naming

- Assertion-методы: is_*, has_*, does_not_*, contains_*, starts_with, ends_with
- Новые assertions следуют существующему паттерну: глагол + предикат
- Тестовые файлы: test_<feature>.py
- Миксины: <Category>Mixin

---

## Testing

- Coverage 100%. Каждый assertion-метод покрыт: happy path, error path, edge cases.
- Тесты используют pytest.raises(AssertionError) для проверки сообщений об ошибках.
- match= в pytest.raises для валидации текста ошибки.
- Snapshot-тесты хранят данные в tests/__snapshots__/.
