"""Parity between the typed Protocols and the concrete ``AssertionBuilder``.

The Protocols in :mod:`assertpy2._typing` are hand-maintained and exist only under ``TYPE_CHECKING``,
so nothing at runtime stops them from advertising a method the concrete builder does not have (or
whose signature no longer accepts the declared arguments).  These tests parse the module with ``ast``
and verify every declared method against the real class, so that drift fails the suite instead of
surfacing as a user's ``AttributeError`` on a method their IDE offered.

The reverse direction (concrete methods absent from any Protocol) is intentionally not asserted: the
Protocols are curated per-type subsets, not mirrors of the full API.
"""

import ast
import inspect
from pathlib import Path

import pytest

import assertpy2._typing
from assertpy2 import assert_that
from assertpy2.assertpy import AssertionBuilder

_SENTINEL = object()


def _protocol_method_cases():
    """Yield ``(protocol_name, method_def)`` for every method declared in a Protocol class."""
    source = Path(assertpy2._typing.__file__).read_text(encoding="utf-8")
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
