"""Parity between the typed Protocols and the concrete ``AssertionBuilder``.

The Protocols in :mod:`assertpy2._engine._typing` are hand-maintained and exist only under ``TYPE_CHECKING``,
so nothing at runtime stops them from advertising a method the concrete builder does not have (or
whose signature no longer accepts the declared arguments).  These tests parse the module with ``ast``
and verify every declared method against the real class, so that drift fails the suite instead of
surfacing as a user's ``AttributeError`` on a method their IDE offered.

The reverse direction is asserted too, per mixin rather than against the whole surface.  Each Protocol
is the narrowed view ``assert_that`` returns for one family of types, so a method added to
``StringMixin`` and not to ``_StringAssertion`` is invisible to every caller holding a ``str`` - it
works at runtime and fails the type check.  A curated subset is still a subset of something, and which
methods are deliberately left out is written below as data rather than as a claim in this docstring.
"""

import ast
import inspect
from pathlib import Path

import pytest

import assertpy2._engine._typing
from assertpy2 import (
    _satisfies,
    assert_that,
    base,
    bytes_mixin,
    collection,
    contains,
    dataframe,
    date,
    dynamic,
    exception,
    extracting,
    file,
    helpers,
    json_mixin,
    numeric,
    snapshot,
    string,
    warning,
)
from assertpy2 import dict as dict_mixin
from assertpy2.assertpy import AssertionBuilder

_SENTINEL = object()

# Which Protocols must, between them, declare every public method of each mixin.  Several mixins are
# reachable from more than one narrowed view (a JSON path assertion applies to a dict and to a list),
# so the requirement is coverage by the union, not membership in one.
_COVERAGE: dict[type, tuple[str, ...]] = {
    base.BaseMixin: ("_CoreAssertion",),
    bytes_mixin.BytesMixin: ("_BytesAssertion",),
    collection.CollectionMixin: ("_IterableAssertion",),
    contains.ContainsMixin: ("_IterableAssertion", "_StringAssertion"),
    date.DateMixin: ("_DateAssertion",),
    dict_mixin.DictMixin: ("_DictAssertion",),
    exception.ExceptionMixin: ("_InvokedAssertion", "_CallableAssertion"),
    extracting.ExtractingMixin: ("_DictAssertion", "_IterableAssertion"),
    file.FileMixin: ("_PathAssertion",),
    json_mixin.JsonMixin: ("_DictAssertion", "_IterableAssertion"),
    numeric.NumericMixin: ("_NumericAssertion",),
    snapshot.SnapshotMixin: ("_CoreAssertion",),
    string.StringMixin: ("_StringAssertion",),
    warning.WarningMixin: ("_CallableAssertion",),
    _satisfies.SatisfiesMixin: ("_IterableAssertion", "_CoreAssertion", "_DictAssertion"),
    dynamic.DynamicMixin: (),
    helpers.HelpersMixin: (),
    dataframe.DataFrameMixin: (),
}

# The one family with no narrowed view, and the reason is structural rather than a matter of extras:
# every ``assert_that`` overload keys on a concrete type (``str``, ``dict``, ``bytes``, ...), and a
# DataFrame or an ndarray matches none of them, so the call resolves to ``AssertionBuilder[_T]``.  That
# fallback is the concrete class, which carries these methods - it is the same path the dynamic
# ``has_*`` assertions take, and it has no Protocol by construction.
_UNTYPED: frozenset[str] = frozenset({"is_array_equal", "is_array_close_to", "is_frame_equal"})


def _protocol_classes():
    """Return ``{name: (own_methods, protocol_bases)}`` for every Protocol in the typed surface."""
    source = Path(assertpy2._engine._typing.__file__).read_text(encoding="utf-8")
    classes = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Assertion"):
            methods = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
            parents = [b.id for b in node.bases if isinstance(b, ast.Name) and b.id.endswith("Assertion")]
            classes[node.name] = (methods, parents)
    return classes


_PROTOCOLS = _protocol_classes()


def _visible(protocol: str) -> set[str]:
    """Everything ``protocol`` offers, its bases included.

    Resolving inheritance is what keeps the reverse check honest: ``is_in`` is declared once on
    ``_CoreAssertion`` and inherited by the rest, so comparing against one class in isolation would
    report methods as missing that every caller can already reach.
    """
    methods, parents = _PROTOCOLS[protocol]
    return set(methods).union(*(_visible(parent) for parent in parents)) if parents else set(methods)


def _public_methods(mixin: type) -> set[str]:
    return {
        name
        for name, value in vars(mixin).items()
        if not name.startswith("_") and (callable(value) or isinstance(value, property))
    }


def _protocol_method_cases():
    """Yield ``(protocol_name, method_def)`` for every method declared in a Protocol class."""
    source = Path(assertpy2._engine._typing.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Assertion"):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    yield node.name, item


_CASES = sorted(_protocol_method_cases(), key=lambda case: (case[0], case[1].name))
_CASE_IDS = [f"{protocol}.{method.name}" for protocol, method in _CASES]


def _is_property(method_def):
    return any(isinstance(dec, ast.Name) and dec.id == "property" for dec in method_def.decorator_list)


def _required_arguments(method_def):
    """Return ``(positional_count, keyword_only_names)`` for the arguments a caller must supply."""
    arguments = method_def.args
    positional = arguments.posonlyargs + arguments.args
    required_positional = len(positional) - len(arguments.defaults) - 1  # minus self
    required_keyword = [
        arg.arg for arg, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True) if default is None
    ]
    return required_positional, required_keyword


class TestProtocolParity:
    def test_collected_a_meaningful_surface(self):
        # guards the collector itself: an ast/refactor slip yielding nothing would pass vacuously
        assert_that(len(_CASES)).is_greater_than(100)
        assert_that({protocol for protocol, _ in _CASES}).contains("_CoreAssertion", "_StringAssertion")

    @pytest.mark.parametrize(("protocol", "method_def"), _CASES, ids=_CASE_IDS)
    def test_declared_method_exists_on_concrete_builder(self, protocol, method_def):
        attribute = inspect.getattr_static(AssertionBuilder, method_def.name, _SENTINEL)
        assert_that(attribute).described_as(
            f"{protocol}.{method_def.name} is advertised to type checkers but missing on AssertionBuilder"
        ).is_not_same_as(_SENTINEL)
        if _is_property(method_def):
            assert_that(isinstance(attribute, property)).is_true()
        else:
            assert_that(callable(attribute)).is_true()

    @pytest.mark.parametrize(
        ("protocol", "method_def"),
        [case for case in _CASES if not _is_property(case[1])],
        ids=[case_id for case_id, case in zip(_CASE_IDS, _CASES, strict=True) if not _is_property(case[1])],
    )
    def test_concrete_signature_accepts_declared_required_arguments(self, protocol, method_def):
        concrete = inspect.getattr_static(AssertionBuilder, method_def.name)
        signature = inspect.signature(concrete)
        positional_count, keyword_names = _required_arguments(method_def)
        positional = [_SENTINEL] * (positional_count + 1)  # plus self
        keyword = dict.fromkeys(keyword_names, _SENTINEL)
        try:
            signature.bind(*positional, **keyword)
        except TypeError as error:
            pytest.fail(f"{protocol}.{method_def.name} declares arguments the concrete method does not accept: {error}")


class TestReverseParity:
    """Every runtime assertion reaches the callers whose type it applies to."""

    def test_every_composed_mixin_is_mapped(self):
        # a new mixin added to the builder and not to the map would otherwise be checked by nothing
        composed = {cls for cls in AssertionBuilder.__mro__ if cls.__name__.endswith("Mixin")}
        assert_that(composed).is_not_empty()
        assert_that({cls.__name__ for cls in composed - set(_COVERAGE)}).described_as(
            "mixins composed into AssertionBuilder but absent from _COVERAGE"
        ).is_empty()
        assert_that({cls.__name__ for cls in set(_COVERAGE) - composed}).described_as(
            "mapped classes no longer composed into AssertionBuilder"
        ).is_empty()

    @pytest.mark.parametrize(
        ("mixin", "protocols"),
        sorted(_COVERAGE.items(), key=lambda item: item[0].__name__),
        ids=sorted(cls.__name__ for cls in _COVERAGE),
    )
    def test_mixin_methods_are_declared_on_its_protocols(self, mixin, protocols):
        covered = set().union(*(_visible(name) for name in protocols)) if protocols else set()
        uncovered = _public_methods(mixin) - covered - _UNTYPED
        assert_that(uncovered).described_as(
            f"{mixin.__name__} methods that work at runtime but no Protocol declares,"
            f" so a caller holding one of these types fails the type check: {sorted(uncovered)}"
        ).is_empty()

    def test_the_untyped_table_holds_only_what_is_still_untyped(self):
        # a stale exemption is the failure mode this whole file exists to prevent, one level up
        declared_anywhere = set().union(*(methods for methods, _ in _PROTOCOLS.values()))
        assert_that(_UNTYPED & declared_anywhere).described_as(
            "exempted from the reverse check but now declared on a Protocol; drop them from _UNTYPED"
        ).is_empty()
        runtime = set().union(*(_public_methods(cls) for cls in _COVERAGE))
        assert_that(_UNTYPED - runtime).described_as("exempted names that no longer exist at runtime").is_empty()

    def test_the_fallback_really_carries_the_untyped_methods(self):
        # the exemption's premise: no overload matches these types, so the call lands on the concrete
        # builder rather than on a narrowed view.  tests/test_typing.py pins that at the type level
        for name in _UNTYPED:
            assert_that(inspect.getattr_static(AssertionBuilder, name, _SENTINEL)).described_as(name).is_not_same_as(
                _SENTINEL
            )
