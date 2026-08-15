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
import itertools
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

# Pairs that say the same thing and must stay apart, with the reason.  Without this the anti-duplication
# gate below would force a shared base for any two matching signatures, and one of those bases already
# widened a type once: lifting the untyped `contains` out of the mapping and the byte string took the
# string's `str | Matcher[str]` with it, so `assert_that("abc").contains(123)` stopped being an error.
_SHARED_ON_PURPOSE: frozenset[tuple[str, str, str]] = frozenset(
    {
        # a mapping searches keys and a byte string searches bytes: one spelling, two questions, and a
        # shared base for them would have to be untyped to fit both
        ("contains", "_BytesAssertion", "_DictAssertion"),
        # narrowing `satisfies` means redeclaring the whole overload pair, and the first half of that
        # pair is the same everywhere by construction: it is the `TypeIs` form the core already has.
        # Only the second half narrows, to `Matcher[str]` and `Matcher[_N]` respectively
        ("satisfies", "_NumericAssertion", "_StringAssertion"),
    }
)

# Where a protocol deliberately redeclares what it inherits in order to narrow it.  The pair of
# overloads has to be repeated whole, so its unchanged half looks like a copy while the other half is
# the entire point: `Matcher[str]` and `Matcher[_N]` instead of the core's `Matcher`.
_NARROWED_ON_PURPOSE: frozenset[tuple[str, str]] = frozenset(
    {("_NumericAssertion", "satisfies"), ("_StringAssertion", "satisfies")}
)

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


def _base_name(base: ast.expr) -> str | None:
    """The name of a protocol base, whether it is written plain or parameterised.

    `_RepeatableAssertion[str]` is a `Subscript`, not a `Name`, and reading only names made this walk
    quietly skip an inherited capability: the reverse check then reported four methods as declared
    nowhere while a caller could reach all four.
    """
    if isinstance(base, ast.Subscript):
        base = base.value
    return base.id if isinstance(base, ast.Name) and base.id.endswith("Assertion") else None


def _protocol_classes():
    """Return ``{name: (own_methods, protocol_bases)}`` for every Protocol in the typed surface."""
    source = Path(assertpy2._engine._typing.__file__).read_text(encoding="utf-8")
    classes = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Assertion"):
            methods = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
            classes[node.name] = (methods, [name for base in node.bases if (name := _base_name(base))])
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


def _inherits(child: str, parent: str) -> bool:
    """Whether `child` reaches `parent` through protocol bases, which makes a repeat inheritance."""
    if child == parent:
        return False
    _methods, parents = _PROTOCOLS[child]
    return parent in parents or any(_inherits(grandparent, parent) for grandparent in parents)


def _declarations_of(protocol: str) -> dict[str, list]:
    """Every method a protocol offers, by name, with *all* declarations of it.

    A list rather than one node, because a name can be an overload group: keeping only the last one made
    every branch but the final invisible to the gates, and a narrowing pair is exactly where a conflict
    would hide.
    """
    declared: dict[str, list] = {}
    for name, method_def in _CASES:
        if name == protocol:
            declared.setdefault(method_def.name, []).append(method_def)
    for parent in _PROTOCOLS[protocol][1]:
        for name, method_defs in _declarations_of(parent).items():
            declared.setdefault(name, method_defs)
    return declared


_CASE_IDS = [f"{protocol}.{method.name}" for protocol, method in _CASES]


def _is_overload_declaration(method_def) -> bool:
    return any(
        isinstance(decorator, ast.Name) and decorator.id == "overload" for decorator in method_def.decorator_list
    )


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


class TestTheProtocolsStayComposed:
    """The capability protocols are only worth having if the duplication cannot quietly come back.

    Six of them exist because fifty-one declarations were copies of each other, and the cheapest way to
    undo that work is to paste a method into two protocols again rather than to give it a home.
    """

    @staticmethod
    def _shape(method_def) -> str:
        """A declaration reduced to what it promises, so formatting and comments do not matter.

        Each parameter carries its kind, because `f(x, /)`, `f(x)` and `f(*, x)` are three different
        promises to a caller, and its default, because a required parameter and one with a default are
        two more.  Flattening those into a list of names would let disagreeing bases pass as identical.

        The normalisation is syntactic, and honestly so: `T | None` and `Optional[T]` mean the same to a
        checker and read as different here.  Catching that would need type evaluation, and this file
        parses text.
        """
        arguments = method_def.args
        positional = arguments.posonlyargs + arguments.args
        padding = [None] * (len(positional) - len(arguments.defaults))
        defaults = dict(zip(positional, padding + list(arguments.defaults), strict=True))
        defaults.update(dict(zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)))

        def one(argument, kind: str) -> str:
            annotation = ast.unparse(argument.annotation) if argument.annotation else "?"
            default = defaults.get(argument)
            return f"{kind}:{argument.arg}:{annotation}" + (f"={ast.unparse(default)}" if default is not None else "")

        parts = [one(argument, "pos-only") for argument in arguments.posonlyargs]
        parts += [one(argument, "pos") for argument in arguments.args]
        if arguments.vararg is not None:
            parts.append(one(arguments.vararg, "var-pos"))
        parts += [one(argument, "kw-only") for argument in arguments.kwonlyargs]
        if arguments.kwarg is not None:
            parts.append(one(arguments.kwarg, "var-kw"))
        returns = ast.unparse(method_def.returns) if method_def.returns else "?"
        return f"({','.join(parts)})->{returns}"

    def test_no_declaration_is_repeated_across_sibling_protocols(self):
        """Every unrelated pair carrying the same signature, not "the group contains one related pair".

        Checking the group as a whole let a repeat between A and B pass whenever some C in the same
        group happened to inherit from A.
        """
        by_shape: dict[tuple[str, str], list[str]] = {}
        for protocol, method_def in _CASES:
            by_shape.setdefault((method_def.name, self._shape(method_def)), []).append(protocol)
        repeated = {
            f"{name} in {left} and {right}": shape
            for (name, shape), protocols in by_shape.items()
            for left, right in itertools.combinations(sorted(protocols), 2)
            if not _inherits(left, right)
            and not _inherits(right, left)
            and (name, left, right) not in _SHARED_ON_PURPOSE
        }
        assert_that(repeated).described_as(
            "identical declarations in protocols that do not inherit from each other: give them a"
            " capability protocol, or record the pair in _SHARED_ON_PURPOSE with the reason"
        ).is_empty()

    def test_a_child_does_not_redeclare_what_it_already_inherits(self):
        # the other way duplication comes back: a copy in a child of what its base already says.  The
        # test above ignores related pairs on purpose, so without this one that route is open
        redundant = {}
        for protocol, method_def in _CASES:
            for parent in _PROTOCOLS[protocol][1]:
                inherited = _declarations_of(parent).get(method_def.name) or []
                if (protocol, method_def.name) in _NARROWED_ON_PURPOSE:
                    continue
                if any(self._shape(one) == self._shape(method_def) for one in inherited):
                    redundant[f"{protocol}.{method_def.name}"] = f"already inherited from {parent}"
        assert_that(redundant).described_as("declarations a protocol repeats from its own base").is_empty()

    def test_a_name_carried_by_two_bases_means_the_same_thing_in_both(self):
        """Multiple inheritance is safe only while the bases agree about a shared name.

        Several protocols now have more than one base.  Two of them declaring the same method
        differently would leave which one wins to the resolution order, which is not something a reader
        should have to work out from the class line.
        """
        conflicts = {}
        for protocol, (_methods, parents) in _PROTOCOLS.items():
            shapes: dict[str, set[str]] = {}
            for parent in parents:
                for name, method_defs in _declarations_of(parent).items():
                    shapes.setdefault(name, set()).add(tuple(self._shape(one) for one in method_defs))
            disagreeing = {name: sorted(forms) for name, forms in shapes.items() if len(forms) > 1}
            if disagreeing:
                conflicts[protocol] = disagreeing
        assert_that(conflicts).described_as("bases of one protocol declaring one name in two shapes").is_empty()

    def test_a_protocol_declares_each_name_once_unless_it_is_an_overload(self):
        """Two plain `def`s of one name in one class: the second silently wins.

        The other gates compare protocols against each other and against their bases, so this way back
        into duplication was open. An overload group is the one legitimate repeat, and it is recognised
        by the decorator rather than allowed by name.
        """
        shadowed = {}
        for protocol in _PROTOCOLS:
            seen: dict[str, list] = {}
            for name, method_def in _CASES:
                if name == protocol:
                    seen.setdefault(method_def.name, []).append(method_def)
            for name, declarations in seen.items():
                plain = [one for one in declarations if not _is_overload_declaration(one)]
                if len(plain) > 1 or (len(declarations) > 1 and plain):
                    shadowed[f"{protocol}.{name}"] = f"{len(declarations)} declarations, {len(plain)} without @overload"
        assert_that(shadowed).described_as("names declared more than once inside one protocol").is_empty()
