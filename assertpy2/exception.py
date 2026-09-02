from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, Final, cast

from ._engine._compat import BaseExceptionGroup
from ._engine._mixin_base import _MixinBase
from ._engine._require import argument, refuse
from .errors import _callable_name, _type_expression_name

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ._engine._compat import Self

__tracebackhide__ = True

_UNSET: Final = object()  # sentinel: no return value / exception captured yet


def _nodes(exc: BaseException) -> Iterator[BaseException]:
    """Every exception in the tree, groups included, the group itself before its members.

    What `BaseExceptionGroup.subgroup()` matches against, in the order it meets them.

    Iterative, and lazy, for the depth: `subgroup()` is written in C and answers on a group nested three
    thousand deep, where a recursive walk in Python gives up around five hundred.  Yielding also lets a
    caller looking for one exception stop at it instead of building the whole tree first.
    """
    pending = [exc]
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, BaseExceptionGroup):
            pending.extend(reversed(node.exceptions))


def _leaves(exc: BaseException) -> list[BaseException]:
    """The same walk without the groups: what actually failed, rather than what holds it."""
    return [node for node in _nodes(exc) if not isinstance(node, BaseExceptionGroup)]


def _require_exception_type(ex: object) -> type[BaseException]:
    """Refuse anything that is not an exception class, in the shape `raises()` already refuses it.

    `isinstance()` and `issubclass()` each report their own argument position and neither names the
    assertion, and `isinstance(node, str)` does not complain at all: it answers False, so a mistyped
    argument would read as "the group does not contain <str>" rather than as the mistake it is.
    """
    if not (isinstance(ex, type) and issubclass(ex, BaseException)):
        refuse(ex, "an exception type", subject=argument("exception"))
    return ex


def _shaped(spec: object, at: str) -> object:
    """Validate one node of a tree spec, returning it, and refuse anything the matcher cannot read.

    A `list` is a subgroup and anything else has to be an exception type.  A `tuple` is refused by name:
    elsewhere in this library a tuple of types means "any of these", and reading it as a subgroup here
    would give one spelling two meanings.
    """
    if isinstance(spec, list):
        if not spec:
            refuse(
                spec,
                f"a non-empty subgroup at {at}, since a group with no members cannot be raised",
                subject=argument("expected"),
            )
        return [_shaped(member, f"{at}[{index}]") for index, member in enumerate(spec)]
    if isinstance(spec, tuple):
        refuse(spec, f"a list for a subgroup at {at}, not a tuple", subject=argument("expected"))
    return _require_exception_type(spec)


def _matches_shape(spec: list[Any], exceptions: tuple[BaseException, ...]) -> bool:
    """Whether every spec entry pairs with a distinct exception, and none is left over.

    A complete matching rather than a greedy walk, and the difference is observable: pairing in the
    order written makes `(Exception, ValueError)` refuse a group of `ValueError` and `KeyError` while
    `(ValueError, Exception)` accepts it, so the same claim would depend on how it was typed.  Measured
    against `pytest.RaisesGroup`, which does pair greedily and refuses the first spelling.

    Recursion is over the *spec*, not the tree: a type entry stops the descent whatever is under it, so
    the depth is what somebody wrote by hand rather than what a task group nested.
    """
    if len(spec) != len(exceptions):
        return False
    candidates = [
        {
            index
            for index, exc in enumerate(exceptions)
            if isinstance(exc, BaseExceptionGroup) and _matches_shape(entry, exc.exceptions)
        }
        if isinstance(entry, list)
        else {index for index, exc in enumerate(exceptions) if isinstance(exc, entry)}
        for entry in spec
    ]
    paired: dict[int, int] = {}
    unpaired = []
    for entry, options in enumerate(candidates):
        free = next((index for index in options if index not in paired), None)
        if free is None:
            unpaired.append(entry)
        else:
            paired[free] = entry
    return all(_augmented(entry, candidates, paired) for entry in unpaired)


def _augmented(entry: int, candidates: list[set[int]], paired: dict[int, int]) -> bool:
    """Whether one spec entry can be paired by displacing others, updating `paired` when it can.

    Iterative, because the chain of displacements is as long as the spec is wide rather than as deep:
    1100 entries of one type over 1100 exceptions of that type recursed past the limit and reported a
    `RecursionError` for a group that matches.
    """
    seen: set[int] = set()
    path: list[tuple[int, Iterator[int]]] = [(entry, iter(candidates[entry]))]
    taken: list[int] = []
    while path:
        options = path[-1][1]
        for index in options:
            if index in seen:
                continue
            seen.add(index)
            taken.append(index)
            if index not in paired:
                for step, (displaced, _) in reversed(list(enumerate(path))):
                    paired[taken[step]] = displaced
                return True
            path.append((paired[index], iter(candidates[paired[index]])))
            break
        else:
            path.pop()
            if taken:
                taken.pop()
    return False


def _naming(spec: list[Any], exc: BaseException) -> dict[int, str]:
    """A name per class across both halves of the message, distinct however alike the classes are.

    Two classes called `Error` from different modules otherwise render a mismatch as two identical trees,
    which reads as the assertion contradicting itself.  Qualifying is enough for those and is applied only
    where the short names collide, following `_disambiguated`: the common case keeps the short name.

    Module and qualified name do not settle it either.  A class defined inside a function has both fixed,
    so two calls to that function give two classes indistinguishable by name, and a reloaded module gives
    the same.  Those get an ordinal, ordered by where they were met rather than by identity, since a set
    of classes iterates differently between runs and a failure message has to read the same twice.

    Keyed by `id`, because a class is only usually hashable: a metaclass setting `__hash__ = None` turned
    the failure into a `TypeError`, where the other three group assertions reported it and carried on.
    """

    def in_spec(entries: list[Any]) -> Iterator[type]:
        for entry in entries:
            yield from in_spec(entry) if isinstance(entry, list) else (cast("type", entry),)

    kinds: dict[int, type] = {}
    for kind in in_spec(spec):
        kinds.setdefault(id(kind), kind)
    for node in _nodes(exc):
        kinds.setdefault(id(type(node)), type(node))
    short = Counter(kind.__name__ for kind in kinds.values())
    qualified = {
        key: f"{kind.__module__}.{kind.__qualname__}" if short[kind.__name__] > 1 else kind.__name__
        for key, kind in kinds.items()
    }
    still_alike = Counter(qualified.values())
    ordinals: Counter[str] = Counter()
    names = {}
    for key, label in qualified.items():
        ordinals[label] += 1
        names[key] = label if still_alike[label] == 1 else f"{label}#{ordinals[label]}"
    return names


def _shape_of(exc: BaseException, names: dict[int, str]) -> str:
    """The tree as names, for the message: a group becomes a bracketed list of what it holds.

    Built as text rather than as a list of strings, because the list would print its names in quotes and
    a reader comparing two trees would be reading around them.

    Iterative, because this runs on the failure path over a tree the program under test built rather than
    over anything written by hand: a group 3000 deep turned the assertion into a `RecursionError`.

    Emitted as pieces joined once, rather than as each node's finished text, because the latter has every
    ancestor holding a copy of its child: 16000 deep cost 123 ms and 258 MB of peak for 32 KB of output.
    """
    pieces: list[str] = []
    pending: list[BaseException | str] = [exc]
    while pending:
        node = pending.pop()
        if isinstance(node, str):
            pieces.append(node)
        elif isinstance(node, BaseExceptionGroup):
            pieces.append("[")
            pending.append("]")
            for position, member in enumerate(reversed(node.exceptions)):
                if position:
                    pending.append(", ")
                pending.append(member)
        else:
            pieces.append(names[id(type(node))])
    return "".join(pieces)


def _spec_shape(spec: object, names: dict[int, str]) -> str:
    """The same rendering for a spec, so the two halves of the message line up."""
    if isinstance(spec, list):
        return f"[{', '.join(_spec_shape(entry, names) for entry in spec)}]"
    return names[id(spec)]


def _escaped(exc: BaseException) -> bool:
    """Whether *exc* is the runner's to act on rather than a mismatch to report.

    A probe interrupted by ``KeyboardInterrupt``, or one that called ``sys.exit()``, did not answer the
    question the assertion asked.  Reported as a mismatch, Ctrl+C turned into a red test, and
    ``does_not_raise()`` swallowed it whole, so neither reached the runner.  Asking for one of them by
    name still works: the caller's own branch catches what it named before this is consulted.
    """
    return not isinstance(exc, Exception)


def _first_of(exc: BaseException, ex: type) -> BaseException | None:
    """The first exception of type *ex* in the tree, or ``None``.

    The one place the three group assertions ask their question, so they cannot answer it differently.
    `BaseExceptionGroup.subgroup()` answers the same on a stock group, but it is a method a subclass may
    override, which would split the verdicts between whichever assertions called it.
    """
    return next((node for node in _nodes(exc) if isinstance(node, ex)), None)


def _effective_cause(exc: BaseException) -> BaseException | None:
    """The exception that chained into *exc*: explicit ``__cause__`` (``raise ... from``), else the
    implicit ``__context__`` (a raise during handling), unless the context was suppressed."""
    if exc.__cause__ is not None:
        return exc.__cause__
    if not exc.__suppress_context__:
        return exc.__context__
    return None


class _InertBuilder:
    """No-op builder returned after a failed raises/when_called_with in soft mode.

    Silently absorbs all chained assertions so they don't crash on wrong val type.
    """

    def __getattr__(self, name):
        return lambda *args, **kwargs: self


class ExceptionMixin(_MixinBase):
    """Expected exception mixin."""

    def raises(self, ex: type) -> Self:
        """Asserts that val is callable and set the expected exception.

        Just sets the expected exception, but never calls val, and therefore never fails. You must
        chain to [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with] to invoke ``val()``.

        Args:
            ex: the expected exception

        Examples:
            Usage:

                assert_that(some_func).raises(RuntimeError).when_called_with('foo')

        Returns:
            AssertionBuilder: returns a new instance (with the expected exception) to chain the next assertion
        """
        if not callable(self.val):
            refuse(self.val, "callable")
        expected = _require_exception_type(ex)

        return self.builder(self.val, self.description, self.kind, expected, self.logger)

    def when_called_with(self, *some_args: object, **some_kwargs: object) -> Self:
        """Asserts that val, when invoked with the given args and kwargs, meets the set expectation.

        Invokes ``val()`` with the given args and kwargs.  You must first set an expectation with
        [`raises()`][assertpy2.exception.ExceptionMixin.raises] or
        [`does_not_raise()`][assertpy2.exception.ExceptionMixin.does_not_raise] (expected exception),
        or with
        [`warns()`][assertpy2.warning.WarningMixin.warns] or
        [`does_not_warn()`][assertpy2.warning.WarningMixin.does_not_warn] (expected warning).

        Args:
            *some_args: the args to call ``val()``
            **some_kwargs: the kwargs to call ``val()``

        Examples:
            Usage:

                def some_func(a):
                    raise RuntimeError('some error!')

                assert_that(some_func).raises(RuntimeError).when_called_with('foo')

        Returns:
            AssertionBuilder: returns a new instance (now with the captured exception or warning
                message as the val) to chain to the next assertion

        Raises:
            AssertionError: if val does **not** meet the set expectation
            TypeError: if no expectation set first
        """
        if self._expected_warning is not None:
            if self._not_expected:
                return self._when_called_with_not_warning(self._expected_warning, *some_args, **some_kwargs)
            return self._when_called_with_warning(self._expected_warning, *some_args, **some_kwargs)

        if not self.expected:
            raise TypeError("no expectation set; call raises(), warns() or a does_not_* method first")

        if getattr(self, "_not_expected", False):
            return self._when_called_with_not_expected(*some_args, **some_kwargs)

        try:
            self.val(*some_args, **some_kwargs)
        except BaseException as e:
            if issubclass(type(e), self.expected):
                captured = self.builder(str(e), self.description, self.kind, logger=self.logger)
                captured._raised_exception = e
                return captured
            elif _escaped(e):
                raise
            else:
                self.error(
                    f"Expected <{_callable_name(self.val)}> to raise <{self.expected.__name__}>"
                    f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)}),"
                    f" but raised <{type(e).__name__}>.",
                    expected=self.expected,
                )
                return cast("Self", _InertBuilder())

        self.error(
            f"Expected <{_callable_name(self.val)}> to raise <{self.expected.__name__}>"
            f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)}).",
            expected=self.expected,
        )
        return cast("Self", _InertBuilder())

    def returned(self) -> Self:
        """Pivots the chain to the value ``val()`` returned during
        [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with].

        Use after a call that completed normally ([`warns()`][assertpy2.warning.WarningMixin.warns],
        [`does_not_warn()`][assertpy2.warning.WarningMixin.does_not_warn], or
        [`does_not_raise()`][assertpy2.exception.ExceptionMixin.does_not_raise]) to assert
        on the return value in the same chain.

        Examples:
            Usage:

                assert_that(make_client).warns(DeprecationWarning).when_called_with().returned().is_instance_of(Client)
                assert_that(adder).does_not_raise(TypeError).when_called_with(1, 2).returned().is_equal_to(3)

        Returns:
            AssertionBuilder: a new instance wrapping the captured return value

        Raises:
            TypeError: if no return value was captured (the call raised, or
                [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with]
                was not invoked first)
        """
        if self._return_value is _UNSET:
            raise TypeError("no return value captured; returned() is only valid after a call that completed normally")
        return self.builder(self._return_value, self.description, self.kind, logger=self.logger)

    def raised(self) -> Self:
        """Pivots the chain to the exception object caught by
        [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with], to assert on its type,
        ``args``, or custom attributes - not only its message string.

        Examples:
            Usage:

                err = assert_that(load).raises(ConfigError).when_called_with("bad").raised().value
                assert_that(err.code).is_equal_to(42)

        Returns:
            AssertionBuilder: a new instance wrapping the caught exception object

        Raises:
            TypeError: if no exception was captured (the call did not raise, or
                [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with] was not invoked first)
        """
        exc = self._require_raised("raised")
        return self.builder(exc, self.description, self.kind, logger=self.logger)

    def caused_by(self, ex: type) -> Self:
        """Asserts the caught exception was chained from a cause of type ``ex`` (``raise ... from``, or an
        exception raised during handling), then pivots the chain to that cause's message.

        Examples:
            Usage:

                assert_that(save).raises(ServiceError).when_called_with(row).caused_by(TimeoutError)

        Args:
            ex: the expected cause type

        Returns:
            AssertionBuilder: a new instance wrapping the cause's message (chain on it, or walk deeper)
        """
        exc = self._require_raised("caused_by")
        cause = _effective_cause(exc)
        if cause is None or not isinstance(cause, ex):
            found = "no cause" if cause is None else f"<{type(cause).__name__}>"
            expected_name = _type_expression_name(ex)
            self.error(
                f"Expected <{type(exc).__name__}> to be caused by <{expected_name}>, but the cause was {found}.",
                expected=ex,
            )
            return cast("Self", _InertBuilder())
        pivoted = self.builder(str(cause), self.description, self.kind, logger=self.logger)
        pivoted._raised_exception = cause
        return pivoted

    def has_root_cause(self, ex: type) -> Self:
        """Asserts the *root* of the caught exception's cause chain is of type ``ex``, then pivots the chain
        to that root cause's message.

        Args:
            ex: the expected root-cause type

        Returns:
            AssertionBuilder: a new instance wrapping the root cause's message
        """
        exc = self._require_raised("has_root_cause")
        root = exc
        seen = {id(root)}
        while (nxt := _effective_cause(root)) is not None and id(nxt) not in seen:
            root = nxt
            seen.add(id(root))
        if not isinstance(root, ex):
            self.error(
                f"Expected <{type(exc).__name__}> to have root cause <{_type_expression_name(ex)}>,"
                f" but the root cause was <{type(root).__name__}>.",
                expected=ex,
            )
            return cast("Self", _InertBuilder())
        pivoted = self.builder(str(root), self.description, self.kind, logger=self.logger)
        pivoted._raised_exception = root
        return pivoted

    def contains_error(self, *ex_types: type) -> Self:
        """Asserts the caught exception is an exception group that contains, recursively, an exception of
        each given type (for [`raises(ExceptionGroup)`][assertpy2.exception.ExceptionMixin.raises]).

        Examples:
            Usage:

                assert_that(run_tasks).raises(ExceptionGroup).when_called_with().contains_error(ValueError, KeyError)

        Args:
            *ex_types: the exception types the group must contain

        Returns:
            AssertionBuilder: this instance, to chain further assertions on the group

        Raises:
            ValueError: if called with no types at all, which nothing could fail
            TypeError: if given anything but an exception class
        """
        if len(ex_types) == 0:
            raise ValueError("one or more args must be given")
        for ex in ex_types:
            _require_exception_type(ex)
        exc = self._require_group("contains_error")
        if exc is None:
            return cast("Self", _InertBuilder())
        for ex in ex_types:
            if _first_of(exc, ex) is None:
                self.error(
                    f"Expected the raised exception group to contain <{ex.__name__}>, but it did not.", expected=ex
                )
                return cast("Self", _InertBuilder())
        return self

    def does_not_contain_error(self, *ex_types: type) -> Self:
        """Asserts the caught exception group holds none of the given types, at any depth.

        The none-of counterpart to [`contains_error()`][assertpy2.exception.ExceptionMixin.contains_error]
        rather than its negation: that one asks for every type given, this one refuses every type given.
        With several arguments both can fail on the same group, which is what "some but not all" means.

        Examples:
            Usage:

                assert_that(run_tasks).raises(ExceptionGroup).when_called_with().does_not_contain_error(KeyError)

        Args:
            *ex_types: the exception types the group must not contain

        Returns:
            AssertionBuilder: this instance, to chain further assertions on the group

        Raises:
            ValueError: if called with no types at all, which nothing could fail
            TypeError: if given anything but an exception class
        """
        if len(ex_types) == 0:
            raise ValueError("one or more args must be given")
        for ex in ex_types:
            _require_exception_type(ex)
        exc = self._require_group("does_not_contain_error")
        if exc is None:
            return cast("Self", _InertBuilder())
        for ex in ex_types:
            if _first_of(exc, ex) is not None:
                self.error(f"Expected the raised exception group to not contain <{ex.__name__}>, but it did.")
                return cast("Self", _InertBuilder())
        return self

    def errors(self) -> Self:
        """Pivots the chain to the list of leaf exceptions in the caught group, nested ones flattened.

        Flattened rather than one level deep, because that is what
        [`contains_error()`][assertpy2.exception.ExceptionMixin.contains_error] already searches: a group
        holding a group is an implementation detail of whoever raised it, and a suite asking "what
        failed" means the leaves.  The view this was reached from still holds the group, so
        [`raised()`][assertpy2.exception.ExceptionMixin.raised] on *that* answers with the whole tree when
        the shape itself is the point.  It is not offered on the leaves, which are a collection.

        Examples:
            Usage:

                assert_that(run_tasks).raises(ExceptionGroup).when_called_with().errors().is_length(2)
                assert_that(run_tasks).raises(ExceptionGroup).when_called_with().errors().extracting(
                    "args"
                ).contains(("bad id",))

        Returns:
            AssertionBuilder: a new instance wrapping the leaves as a list, to ask a collection anything

        Raises:
            TypeError: if no exception was captured
        """
        exc = self._require_group("errors")
        if exc is None:
            return cast("Self", _InertBuilder())
        return self.builder(_leaves(exc), self.description, self.kind, logger=self.logger)

    def error_of(self, ex: type) -> Self:
        """Asserts the caught group holds an exception of type ``ex``, then pivots to that one's message.

        The step [`contains_error()`][assertpy2.exception.ExceptionMixin.contains_error] cannot take: after
        it the chain still holds the *group's* message, so asking what one failure said meant reaching into
        the tree by hand.

        Both search the same exceptions, groups included, so whatever one finds the other pivots to.  Asking
        for a group type therefore answers with that group, and for the outermost one that is the message
        the chain already held.

        Examples:
            Usage:

                assert_that(run_tasks).raises(ExceptionGroup).when_called_with().error_of(ValueError).contains("bad id")

        Args:
            ex: the type to pivot to, the first one found, the group itself before its members

        Returns:
            AssertionBuilder: a new instance wrapping that exception's message (chain on it, or
                `raised()` to reach the object itself)

        Raises:
            TypeError: if given anything but an exception class
        """
        _require_exception_type(ex)
        exc = self._require_group("error_of")
        if exc is None:
            return cast("Self", _InertBuilder())
        found = _first_of(exc, ex)
        if found is None:
            self.error(f"Expected the raised exception group to contain <{ex.__name__}>, but it did not.", expected=ex)
            return cast("Self", _InertBuilder())
        pivoted = self.builder(str(found), self.description, self.kind, logger=self.logger)
        pivoted._raised_exception = found
        return pivoted

    def matches_error_tree(self, *expected: type | list[Any]) -> Self:
        """Asserts the caught group holds exactly these exceptions, in exactly this nesting.

        The question [`contains_error()`][assertpy2.exception.ExceptionMixin.contains_error] does not ask.
        That one searches the whole tree for a type and says nothing about how many others there are or
        how deep it sat, so a group that grew an extra failure, or one whose members moved into a
        subgroup, still passes it.  This one reads the shape.

        A `list` is a subgroup and a type is one exception, so `(ValueError, [KeyError])` means a group of
        two members whose second is a subgroup holding one `KeyError`.  A type matches by `isinstance`,
        the way the rest of the family does, so `Exception` matches a subgroup node as readily as a leaf,
        and stops there: only a nested list looks inside one, and what a matched subgroup holds is unsaid.

        Order is not part of the shape.  Whoever raised the group usually did not choose it: an
        `asyncio.TaskGroup` reports its failures in the order the tasks finished.

        Examples:
            Usage:

                assert_that(run_tasks).raises(ExceptionGroup).when_called_with().matches_error_tree(
                    ValueError, [KeyError, KeyError]
                )

        Args:
            *expected: one entry per member of the group, a type for an exception and a list for a
                subgroup

        Returns:
            AssertionBuilder: this instance, to chain further assertions on the group

        Raises:
            ValueError: if called with no entries at all, as the rest of the family does
            TypeError: if an entry is neither an exception class nor a list, or is an empty list, which
                is a group with no members and cannot be raised
        """
        if not expected:
            raise ValueError("one or more args must be given")
        spec = [_shaped(entry, f"[{index}]") for index, entry in enumerate(expected)]
        exc = self._require_group("matches_error_tree")
        if exc is None:
            return cast("Self", _InertBuilder())
        if not _matches_shape(spec, exc.exceptions):
            names = _naming(spec, exc)
            self.error(
                f"Expected the raised exception group to match <{_spec_shape(spec, names)}>,"
                f" but it was <{_shape_of(exc, names)}>.",
                expected=spec,
            )
            return cast("Self", _InertBuilder())
        return self

    def _require_group(self, method: str) -> Any:
        """The caught exception as a group, or ``None`` after reporting that it was not one.

        Returns ``Any`` rather than the group type: on the 3.10 floor the compat name falls back to an
        empty tuple, which is a value and not a type, so an annotation naming it is rejected outright.
        Callers walk `.exceptions` on the result, which is why the check has to happen before they do.
        """
        exc = self._require_raised(method)
        if not isinstance(exc, BaseExceptionGroup):
            self.error(f"Expected the raised <{type(exc).__name__}> to be an exception group, but it was not.")
            return None
        return exc

    def _require_raised(self, method: str) -> BaseException:
        if self._raised_exception is _UNSET:
            raise TypeError(
                f"no exception captured; {method}() is only valid after raises()...when_called_with() caught one"
            )
        return cast("BaseException", self._raised_exception)

    def _when_called_with_not_expected(self, *some_args, **some_kwargs) -> Self:
        expected = cast("type[BaseException]", self.expected)  # when_called_with() rejects an unset expectation
        try:
            result = self.val(*some_args, **some_kwargs)
        except BaseException as e:
            if issubclass(type(e), expected):
                self.error(
                    f"Expected <{_callable_name(self.val)}> to not raise <{expected.__name__}>"
                    f" when called with ({self._fmt_args_kwargs(*some_args, **some_kwargs)}),"
                    f" but did raise <{type(e).__name__}>."
                )
                return cast("Self", _InertBuilder())
            if _escaped(e):
                raise
            return self
        self._return_value = result
        return self

    def does_not_raise(self, ex: type) -> Self:
        """Asserts that val is callable and sets the not-expected exception.

        Just sets the not-expected exception, but never calls val. You must
        chain to [`when_called_with()`][assertpy2.exception.ExceptionMixin.when_called_with] to invoke ``val()``.

        Args:
            ex: the exception that should **not** be raised

        Examples:
            Usage:

                assert_that(some_func).does_not_raise(RuntimeError).when_called_with('foo')

        Returns:
            AssertionBuilder: returns a new instance to chain to the next assertion
        """
        if not callable(self.val):
            refuse(self.val, "callable")
        unwanted = _require_exception_type(ex)

        new_builder = self.builder(self.val, self.description, self.kind, unwanted, self.logger)
        new_builder._not_expected = True
        return new_builder
