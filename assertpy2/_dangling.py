"""Find `assert_that(...)` statements that assert nothing.

Two shapes pass every test runner in silence:

    assert_that(items)              # a builder is built and thrown away
    assert_that(items).is_empty     # the assertion is looked up and never called

Neither can happen with a bare ``assert``, so a fluent API owes its users a way to catch them.  The
second shape is already reported by ruff's B018 (useless attribute access); the first is not reported
by anything, because a call may have side effects and no linter can know this one does not.

The check is static and runs at collection.  A runtime version was tried first and rejected: marking
the builder from a wrapper adds a stack frame, and `snapshot()` / `matches_inline()` resolve their
caller with a single `f_back` hop from inside the method body (see `_require_caller` in snapshot.py,
whose docstring says exactly why the hop count must not move).  Reading the source costs nothing at
runtime and cannot shift a frame.

What it deliberately does not flag:

* a builder bound to a name (`b = assert_that(x)`), because whether `b` is used later is not a
  question about this statement;
* a chain that ends on a pivot (`.described_as(...)`, `.extracting(...)`), because the set of
  assertions is a runtime property of the builder and hard-coding it here would rot;
* `assert_conforms()`, `fail()`, `soft_fail()`, which assert on their own rather than returning a
  builder, so a bare call to them is correct usage.
"""

from __future__ import annotations

import ast
import io
import tokenize
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterator

__tracebackhide__ = True

# the builder factories, and only those: everything else in the package's public surface either
# asserts by itself or is not an entry point at all
_ENTRY: Final = frozenset({"assert_that", "assert_warn"})
_PACKAGE: Final = "assertpy2"

ALLOW_MARKER: Final = "assertpy2: allow-dangling"
"""Comment that silences one statement, for the cases where asserting nothing is the point.

They exist and they are not mistakes: a benchmark measuring what building a builder costs, a test of
this library's own machinery, a snippet written to demonstrate the shape.  Without a way to say so, the
only answer to one deliberate line is turning the whole check off, and a check that has to be switched
off wholesale is a check nobody runs.
"""

_NO_ASSERTION: Final = "{name}() builds a builder here and asserts nothing"
"""Template rather than a sentence: the message names the call as the reader wrote it.

A project that registered its own wrapper reads `check(1)` on the offending line, and being told about
`assert_that()` there costs a moment of "that is not what my code says" on every finding.
"""
_NOT_CALLED: Final = "assertion is looked up and never called (missing parentheses)"


class Finding(NamedTuple):
    """One offending statement.

    ``path`` and ``lineno`` locate it and ``message`` says which shape it is.  ``scope`` is the chain of
    names around it, ``("TestOne", "test_same")``, so the report reaches the test that contains the line
    rather than another test of the same name: under ``filterwarnings = ["error"]`` the difference is
    which test goes red, and with two same-named methods it was the difference between a finding being
    reported and being dropped.

    Empty for a statement at module scope, which belongs to no test at all.
    """

    path: str
    lineno: int
    message: str
    scope: tuple[str, ...]


class _Bindings(NamedTuple):
    """The names in one module that reach an entry point: bare (`assert_that`) and dotted (`ap.`)."""

    direct: frozenset[str]
    modules: frozenset[str]

    def __bool__(self) -> bool:
        return bool(self.direct or self.modules)


def _rebound(tree: ast.Module) -> frozenset[str]:
    """Names this module binds itself, whatever it also imported under them.

    A fixture parameter named `assert_that`, a local `assert_that = lambda ...`, a module-level
    rebinding: in each of those the call in the body is not this library's, and reporting it is a false
    alarm on somebody else's function.

    Deliberately module-wide rather than scope-aware.  One shadowed parameter disables the check for
    that name across the file, which costs findings and cannot invent them, and the alternative is a
    scope tracker inside what is meant to stay a small static pass.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        # kept apart from the branch below, whose body is identical: merging them into one `or` is what
        # ruff asks for and what a type checker then rejects, since `ExceptHandler.name` is `str | None`
        # and only the separate branch narrows it
        elif isinstance(node, ast.ExceptHandler) and node.name:  # noqa: SIM114
            names.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return frozenset(names)


def _bindings(tree: ast.Module, extra: frozenset[str] = frozenset()) -> _Bindings:
    """Resolve how this module spells the entry points, `as` aliases and star imports included.

    A module that never imports one is skipped whole: a user function of their own named
    `assert_that` must not be reported.

    ``extra`` holds the names a project declared for its own wrapper around `assert_that`.  Those come
    from the project rather than from here, so they are matched whatever module they are imported from,
    and only through `from ... import`: a wrapper reached as `helpers.check(...)` is not recognised, and
    neither is a local `def check` in a module that never imported one.  Requiring the import is the
    whole guard against claiming somebody else's identically named function.
    """
    direct: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            ours = (node.module or "").split(".")[0] == _PACKAGE
            for alias in node.names:
                if alias.name == "*" and ours:
                    direct |= _ENTRY  # the docs' own preamble; a star import binds every entry point
                elif alias.name in extra or (ours and alias.name in _ENTRY):
                    direct.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == _PACKAGE:
                    modules.add(alias.asname or alias.name.split(".")[0])
    shadowed = _rebound(tree)
    return _Bindings(frozenset(direct) - shadowed, frozenset(modules) - shadowed)


def _entry_call(node: ast.expr, bindings: _Bindings) -> str | None:
    """The call's name as written, for `assert_that(...)` however this module spells it, else ``None``.

    The name comes back rather than a flag so the report can quote the reader's own spelling, which is
    the only one they can search for.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id if func.id in bindings.direct else None
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        reaches = func.attr in _ENTRY and func.value.id in bindings.modules
        return f"{func.value.id}.{func.attr}" if reaches else None
    return None


def _reaches_entry(node: ast.expr, bindings: _Bindings) -> bool:
    """True when an attribute chain bottoms out in an entry call, however deep it is nested.

    `assert_that(x).is_equal_to` is one hop, `assert_that(x).not_.is_none` is two, and a chain that
    starts anywhere else (`self.helper.attr`) is none.
    """
    current: ast.expr = node
    while True:
        if _entry_call(current, bindings):
            return True
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Attribute):
            current = current.value
        else:
            return False


def _statements(tree: ast.Module) -> Iterator[tuple[ast.Expr, tuple[str, ...]]]:
    """Every expression statement with the scope it sits in, as the chain of names around it.

    An expression statement is the only place a discarded builder can appear: anywhere else the value
    is bound, passed or returned, and whether *that* asserts is not a question about this statement.

    The scope is a chain rather than one name because a bare name does not identify a test: two classes
    in one file may each define `test_same`, and matching on the name alone handed both findings to
    whichever ran first.  Classes are walked for the same reason, so the chain reads
    ``("TestOne", "test_same")``.
    """
    stack: list[tuple[ast.AST, tuple[str, ...]]] = [(tree, ())]
    while stack:
        node, scope = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                stack.append((child, (*scope, child.name)))
            else:
                if isinstance(child, ast.Expr):
                    yield child, scope
                stack.append((child, scope))


def _marked_lines(source: str) -> frozenset[int]:
    """Line numbers whose *comment* carries the marker.

    Tokenised rather than searched for as text, which was the first implementation and silenced any
    statement holding the marker's own words in a string:
    ``assert_that("# assertpy2: allow-dangling")`` reported nothing.  A test asserting on text that
    quotes the marker is exactly the kind of line a reader would never suspect of being exempt.

    A file that tokenises differently from how it parsed yields nothing rather than raising: the parse
    already succeeded, so the check goes on without the escape hatch instead of taking the run down.
    """
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        return frozenset(one.start[0] for one in tokens if one.type == tokenize.COMMENT and ALLOW_MARKER in one.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):  # pragma: no cover - parse ran first
        return frozenset()


def _silenced(statement: ast.Expr, marked: frozenset[int]) -> bool:
    """Whether the statement carries the marker on any of its own lines.

    Every line the statement spans counts, so the marker can sit at the end of a call broken over
    several lines, which is where a reader would naturally put it.
    """
    last = getattr(statement, "end_lineno", statement.lineno) or statement.lineno
    return any(line in marked for line in range(statement.lineno, last + 1))


def findings(source: str, path: str, extra_entries: frozenset[str] = frozenset()) -> list[Finding]:
    """Report the offending statements in one module's source.

    A statement carrying `ALLOW_MARKER` in a comment is left out: see that constant for why the
    escape hatch has to exist.

    ``extra_entries`` names a project's own wrappers around `assert_that`.  Only list a wrapper that
    *builds* something to assert on: a helper that asserts inside the call itself is not dangling when
    written as a statement, and listing it would report correct code.

    Raises:
        SyntaxError: if *source* does not parse; the caller decides whether that is its problem.
    """
    tree = ast.parse(source)
    bindings = _bindings(tree, extra_entries)
    if not bindings:
        return []
    marked = _marked_lines(source)
    found: list[Finding] = []
    for statement, scope in _statements(tree):
        if _silenced(statement, marked):
            continue
        value = statement.value
        while isinstance(value, ast.Await):  # `await assert_that(x).eventually()...` unwraps to the chain
            value = value.value
        if name := _entry_call(value, bindings):
            found.append(Finding(path, statement.lineno, _NO_ASSERTION.format(name=name), scope))
        elif isinstance(value, ast.Attribute) and _reaches_entry(value, bindings):
            found.append(Finding(path, statement.lineno, _NOT_CALLED, scope))
    return sorted(found, key=lambda finding: finding.lineno)
