"""Recursive diff engine shared by the equality assertions and the dict error path.

Three walkers coexist on purpose and must not be merged: `_build_equality_diff()` dispatches a
top-level pair (top-level dicts are handled by `HelpersMixin._dict_err()` instead, so its ladder
starts at namedtuples), `_Walk.children()` decomposes nested values (mappings first), and
`_walk_leaves()` iterates scalar leaves for the recursive leaf assertions.  Their dispatch orders
differ deliberately; a shared type classifier was investigated and rejected, because a single global
precedence changes behavior for values that quack like several container shapes at once.
The per-shape walks of `_Walk` are the pieces genuinely shared by the two diff ladders.

The three ladders are not the same width, and the reason is worth stating because it has already cost
two bugs.  They answer different questions.  `_build_equality_diff()` asks *how should a difference
here be shown*, so it carries steps that are renderers rather than decompositions: a set diffs by
membership, a string or bytes goes through ``difflib``.  `_sub_diff_entries()` asks *does this value
break into path-addressed entries*, which a set does not, because its members have no stable position
to name.  They agree on mappings and sequences and disagree at both ends: the top has sets, strings and
bytes that the nested walker refuses, and the nested one has mappings that the top never sees, since a
top-level dict is routed to `HelpersMixin._dict_err()` before it gets here.

So do **not** write a predicate that answers "will this decompose".  Two attempts have been made and
both produced a false failure on values that were equal, because the predicate drifted from one ladder
or answered for the wrong one.  Ask the walker and read its answer instead: ``None`` from
`_sub_diff_entries()`, or the ladder falling through to the scalar case in `_build_equality_diff()`.
`_Walk.descend()` is where that reading is interpreted.
"""

from __future__ import annotations

import collections
import dataclasses
import decimal
import difflib
from typing import TYPE_CHECKING, Any, TypeVar

from ..errors import DiffEntry, DiffResult, _safe_repr
from ._compare import _EQ_ATOMIC, _guarded_equal, _node_decision
from ._introspection import (
    TakenApart,
    is_attrs_instance,
    is_mapping_like,
    is_model_dump_object,
    is_namedtuple,
    keyed_names,
    keyed_pair,
    keyed_snapshot,
    model_field_values,
)
from ._ordering import equals, held_key, lookup, member
from ._path import _ROOT, _Path

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Hashable, Iterable, Iterator

    from ._compare import _CompareConfig

    _Frame = tuple[Iterator[Any], int, int]
    """A container's children still to walk, and the ids of the pair it put on the path."""

_K = TypeVar("_K", bound="Hashable")  # a mapping key or a field name, kept as itself through the walk
_T = TypeVar("_T")

__tracebackhide__ = True


def _field_dict(obj, is_model):
    """Field mapping of a pydantic-style model or an attrs instance (shallow), as the values its fields hold.

    An attrs instance's carries the keys its fields are compared through, so the walk decides a field by the
    key both sides declare and still shows the values held: ``str.lower`` would otherwise print a value
    neither side has, and listed a field ``==`` holds equal.
    """
    if is_model:
        return model_field_values(obj)
    compared = [field for field in obj.__attrs_attrs__ if field.eq is not False]
    return TakenApart(
        type(obj),
        {field.name: getattr(obj, field.name) for field in compared},
        {field.name: field.eq_key for field in compared if getattr(field, "eq_key", None) is not None},
    )


def _child_entries(actual, expected, path: _Path, *, descended_for, config=None) -> list[DiffEntry]:
    """The entries of one child, walked on its own by a caller outside a walk.

    `_Walk.descend()` is where the walker's answer for the child is read, given why it was descended into.
    """
    walk = _Walk(config)
    frame = walk.descend(actual, expected, path, descended_for)
    return walk.entries if frame is None else walk.run(*frame)


_ALIGN_MAX_ELEMENTS = 1000
"""Longest sequence `_alignment_opcodes()` will align.

difflib's search is quadratic, and the alignment buys nothing a reader of a thousand-element failure
was going to use anyway, so past this the diff stays positional: never wrong, only longer.
"""


def _alignment_opcodes(actual, expected):
    """difflib opcodes pairing two sequences, or ``None`` when only positions are available.

    Alignment decides *which elements to pair*, never whether a pair is equal - that stays with
    `_node_decision()`, which is what keeps a comparator, a tolerance and ``strict_types`` in charge of
    the verdict no matter how the pairing was found.

    Elements difflib cannot hash - dicts, lists, arrays, which is the shape of most API payloads - are
    aligned on their reprs instead.  A repr stands in for structural identity here, and standing in
    badly costs only a worse pairing, not a wrong answer.  ``autojunk`` is off because the heuristic
    calls any value filling more than 1% of a 200+ element sequence junk, which is exactly the repeated
    value an alignment has to match on.

    `_rechecked_equal_runs()` is what makes the first paragraph true rather than merely intended, and
    both branches go through it: neither of difflib's two notions of a match is this library's.  The
    repr keying matches values that print alike, and the hashable keying matches through a dict lookup,
    while every verdict here is reached by `_node_decision()`.

    The length cap lives in the caller, which reaches it before paying for anything here.
    """
    try:
        opcodes = difflib.SequenceMatcher(None, actual, expected, autojunk=False).get_opcodes()
    except (TypeError, ValueError, decimal.InvalidOperation, OverflowError):  # `difflib` asks `==` itself
        pass
    else:
        return _rechecked_equal_runs(opcodes, actual, expected)
    try:
        keyed_actual = [_safe_repr(item) for item in actual]
        keyed_expected = [_safe_repr(item) for item in expected]
        opcodes = difflib.SequenceMatcher(None, keyed_actual, keyed_expected, autojunk=False).get_opcodes()
    # pragma: no cover - `_safe_repr` swallows everything; what is left degrades to a positional diff
    except (TypeError, ValueError):  # pragma: no cover
        return None
    return _rechecked_equal_runs(opcodes, actual, expected)


def _rechecked_equal_runs(opcodes, actual, expected):
    """Opcodes whose ``equal`` runs survive the comparison this library reaches its verdicts with.

    A run difflib calls equal was matched on whatever it was keyed with, and neither key is the
    verdict.  Keyed on reprs, the run is only known to *print* the same, and a shared repr is not
    exotic: `_safe_repr()` renders every value of a type whose ``__repr__`` raises as the same string.
    Kept, the pair would drop out of the diff and out of the message's elision, and the failure would name
    a smaller difference than the one that caused it.  Keyed on the values, the run matched by identity or
    ``==``, which is already the walk's own rule for an element.

    Compared through `_guarded_equal()`, the same question `_node_decision()` reaches its verdict with, so
    a run split back into a substitution is exactly a pair the walk will then report.  That
    costs one comparison per matched element, on the failing path only and under the caller's length
    cap.  Measured on 200 records with one inserted at the head: 0.38 ms to 0.48 ms for unhashable rows,
    and 0.15 ms to 0.20 ms for hashable ones, which is the path most sequences take.
    """
    revalidated = []
    for tag, actual_start, actual_stop, expected_start, expected_stop in opcodes:
        if tag != "equal":
            revalidated.append((tag, actual_start, actual_stop, expected_start, expected_stop))
            continue
        holds = [
            _guarded_equal(actual[actual_start + offset], expected[expected_start + offset])
            for offset in range(actual_stop - actual_start)
        ]
        run_start = 0
        for offset in range(1, len(holds) + 1):
            if offset < len(holds) and holds[offset] == holds[run_start]:
                continue
            revalidated.append(
                (
                    "equal" if holds[run_start] else "replace",
                    actual_start + run_start,
                    actual_start + offset,
                    expected_start + run_start,
                    expected_start + offset,
                )
            )
            run_start = offset
    return revalidated


def _aligned_match_indices(seq, counterpart) -> set[int] | None:
    """Indices of ``seq`` that align with an equal element of ``counterpart``, or ``None`` if unaligned.

    Lets the failure message collapse a matched run the way the diff collapses it: without this the
    message elides on position and an element inserted at the head shifts every later element out of
    the elision, so the message dumps both sequences whole while the diff below it shows one entry.
    """
    opcodes = _alignment_opcodes_if_useful(seq, counterpart)
    if opcodes is None:
        return None
    matched: set[int] = set()
    for tag, start, stop, _, _ in opcodes:
        if tag == "equal":
            matched.update(range(start, stop))
    return matched


class _Reads:
    """One side of a sequence pair, read as the walk always read it, and through its storage once a read refuses.

    The verdict is in before the walk starts, and `==` of a `list` or `tuple` may never have asked the value's own
    `__len__`, `__getitem__` or `__iter__`: the base one compares the stored items.  A read that refuses there cannot
    be allowed to turn the failure into the value's exception.  Reads that answer pass through untouched, in the
    order and number the walk makes them; from the first refusal on, the stored items answer.  A value with no storage
    behind it, one only posing as a list, keeps its refusal.
    """

    __slots__ = ("sequence",)

    def __init__(self, sequence: Any) -> None:
        self.sequence = sequence

    def _stored(self) -> bool:
        """Whether the stored items now answer in place of the value's own reads."""
        held: Any = self.sequence
        if issubclass(type(held), list):
            self.sequence = list(list.__iter__(held))
        elif issubclass(type(held), tuple):
            self.sequence = list(tuple.__iter__(held))
        else:
            return False
        return True

    def __len__(self) -> int:
        try:
            return len(self.sequence)
        except Exception:
            if not self._stored():
                raise
            return len(self.sequence)

    def __getitem__(self, index: Any) -> Any:
        try:
            return self.sequence[index]
        except Exception:
            if not self._stored():
                raise
            return self.sequence[index]

    def __iter__(self) -> Iterator[Any]:
        # asked out here: a `StopIteration` refusing the iterator inside a generator would become `RuntimeError`
        try:
            iterator = iter(self.sequence)
        except Exception:
            if not self._stored():
                raise
            return iter(self.sequence)
        return self._continued(iterator)

    def _continued(self, iterator: Iterator[Any]) -> Iterator[Any]:
        # `next()` and not a `for`, which would ask the iterator for an iterator of its own first
        read = 0
        while True:
            try:
                item = next(iterator)
            except StopIteration:
                return
            except Exception:
                if not self._stored():
                    raise
                yield from self.sequence[read:]
                return
            read += 1
            yield item


def readable(sequence: Any) -> Any:
    """*sequence*, or for anything but an exact `list` or `tuple` the `_Reads` of it."""
    kind = type(sequence)
    return sequence if kind is list or kind is tuple else _Reads(sequence)


def _positional_difference_count(actual, expected) -> int:
    """How many positions the two sequences differ at when paired by index.

    Guarded rather than bare ``==``: an array member reached here has an element-wise ``==`` with no
    single truth value, and the operand gate on the assertion never saw it - the top-level ``==`` that
    admitted the failure short-circuited on an earlier element.  Without the guard numpy's own
    ``ValueError`` leaves the library in place of the actionable ``TypeError`` it promises.
    """
    return sum(
        1
        for index in range(max(len(actual), len(expected)))
        if index >= len(actual) or index >= len(expected) or not _guarded_equal(actual[index], expected[index])
    )


def _aligned_difference_count(opcodes) -> int:
    """How many positions the alignment reports, which is what an aligned walk would emit."""
    return sum(
        max(actual_stop - actual_start, expected_stop - expected_start)
        for tag, actual_start, actual_stop, expected_start, expected_stop in opcodes
        if tag != "equal"
    )


def _alignment_opcodes_if_useful(actual, expected):
    """Alignment opcodes, or ``None`` when pairing by index already reads at least as short.

    The order matters for cost, not just for the answer.  A long list of records with one field changed
    is the common failure, and pairing it by index already yields the one entry an alignment could -
    but the elements are unhashable, so asking difflib means rendering every element's repr first.  One
    differing position cannot be beaten, so that case never asks: measured on 200 records, it is the
    difference between 0.09 ms and 0.75 ms.

    Alignment is a large win when a sequence shifted and a loss when it did not: a reversal reads as
    two substitutions positionally and as four insertions and deletions aligned.  Counting both, and
    keeping the index reading on a tie, is what lets one rule serve both - and it answers whether a
    tuple should align without a special case, since a coordinate pair is never shorter aligned.

    Counted on ``==`` alone rather than on the built entries: the walkers recurse, so building both to
    compare them would double the work at every level of nesting.  Measured over 13 600 random pairs,
    this count picks the same winner as the exact one every time.
    """
    if len(actual) == len(expected):
        # equal lengths hide a rotation, worth 8% of the wins over 13 640 pairs against a doubled comparison
        return None
    if max(len(actual), len(expected)) > _ALIGN_MAX_ELEMENTS:
        return None  # over the cap nothing here can be used anyway
    positional = _positional_difference_count(actual, expected)
    if positional <= 1:
        return None  # nothing to win: an alignment would have to report zero positions to beat it
    opcodes = _alignment_opcodes(actual, expected)
    if opcodes is None or _aligned_difference_count(opcodes) >= positional:
        return None
    return opcodes


def _ordered_keys(actual: Iterable[_K], expected: Iterable[_K]) -> list[_K]:
    """Every key of both sides, in the order a reader wrote them.

    A union of two sets loses insertion order, which is why this used to be sorted: without an order
    imposed, the report varied with the hash seed.  Sorting bought determinism at the price of the one
    ordering that carries meaning - a JSON response reads in the order its fields arrived, and `k0, k1,
    k10, k100` reads as no order at all.  Walking the actual side and then the keys only the expected
    side has is just as deterministic, and it is the order pytest shows.
    """
    seen = set(actual)
    return [*actual, *(key for key in expected if not member(key, seen))]


def _order_entries(actual, expected, kept, kept_expected, prefix: _Path) -> list[DiffEntry]:
    """The key order of two `OrderedDict` values holding the same keys in different places, which their `==` reads."""
    if not (isinstance(actual, collections.OrderedDict) and isinstance(expected, collections.OrderedDict)):
        return []
    if not equals(set(kept), set(kept_expected)) or equals(list(kept), list(kept_expected)):
        return []
    return [prefix.leaf_entry(actual=list(kept), expected=list(kept_expected))]


class _Walk:
    """One structural diff, walked on a list of frames rather than on the interpreter's stack.

    A frame is the generator over one container's children.  It appends what it finds to ``entries``, yields the
    frame of each child it has to descend into, and is resumed once that child is done.  Walked by recursion,
    every level cost three Python calls, and a pair nested four hundred levels deep raised `RecursionError` in
    place of its failure.

    ``on_path`` holds the current node's ancestors and nothing else, one mapping for the whole walk: a pair
    goes on when its frame opens and comes off when the frame is done.  A copy per level made memory quadratic
    in the depth.  Being on the path is what makes a reference circular, and a value two siblings share is
    not one.  Held by id, and the id holds its value, so no ancestor is freed for a new value to take its id.
    """

    __slots__ = ("config", "entries", "on_path")

    def __init__(self, config: _CompareConfig | None, on_path: Iterable[int] = ()) -> None:
        self.config = config
        self.entries: list[DiffEntry] = []
        self.on_path: dict[int, object] = {}
        self.on_path.update(dict.fromkeys(on_path))

    def run(self, children: Iterator[_Frame], left: int, right: int) -> list[DiffEntry]:
        """Walk *children* to the end, and every frame they open, and answer the entries found."""
        stack = [(children, left, right)]
        on_path = self.on_path
        while stack:
            walking, left, right = stack[-1]
            try:
                nested = next(walking, None)
            except RuntimeError as error:
                escaped = _escaped_stop(error)
                if escaped is None:
                    raise
            else:
                if nested is None:
                    stack.pop()
                    on_path.pop(left, None)
                    on_path.pop(right, None)
                else:
                    stack.append(nested)
                continue
            raise escaped
        return self.entries

    def opened(self, actual, expected, prefix: _Path) -> _Frame | None:
        """The frame over a pair's children with the pair now on the path, or ``None`` for a pair not taken apart."""
        children = self.children(actual, expected, prefix)
        if children is None:
            return None
        left, right = id(actual), id(expected)
        self.on_path[left] = actual
        self.on_path[right] = expected
        return children, left, right

    def descend(self, actual, expected, path: _Path, descended_for) -> _Frame | None:
        """Walk into a child, given *why* it was descended into: its entries, or the frame still to walk.

        `_Walk.children()` answers ``None`` for a value it does not take apart, and that answer means
        two different things depending on the reason for the descent.  Descending because the two sides
        differ, ``None`` is a differing leaf and must be reported.  Descending because ``strict_types`` has
        to look past a container whose own ``==`` was true, ``None`` is a value that is already equal and
        must not be.  Reading it wrong is where the false failure on two equal sets came from, so the two
        readings live here and nowhere else: every caller names its reason.

        Scope, because this is easy to over-read: it owns ``None`` for *building entries*, not for every
        use of the walker.  Two other readings exist and are both correct for their own job -
        `assertpy2._engine._equality.values_differ()` treats ``None`` as "ask ``==`` instead", and
        `HelpersMixin._dict_err()` treats it as "nothing to render".  A new caller still has to decide what
        ``None`` means for what it is doing; it just must not invent a fourth answer for this one.
        """
        if id(actual) in self.on_path or id(expected) in self.on_path:
            self.entries.append(path.entry(actual="<circular ref>", expected="<circular ref>"))
            return None
        frame = self.opened(actual, expected, path)
        if frame is None and descended_for != "strict":
            self.entries.append(path.entry(actual=actual, expected=expected))
        return frame

    def children(self, actual, expected, prefix: _Path) -> Iterator[_Frame] | None:
        """The walk over a pair's children, in the nested ladder, or ``None`` for a pair it does not take apart.

        Mappings, dataclasses, namedtuples, model-dump objects, attrs instances and sequences are taken
        apart.  The ladder starts at mappings, where `_build_equality_diff()` starts at namedtuples.
        """
        if is_mapping_like(actual) and is_mapping_like(expected):
            return self.mapping(actual, expected, prefix)
        if (
            dataclasses.is_dataclass(actual)
            and not isinstance(actual, type)
            and dataclasses.is_dataclass(expected)
            and not isinstance(expected, type)
        ):
            return self.dataclass(actual, expected, prefix)
        if is_namedtuple(actual) and is_namedtuple(expected):
            return self.namedtuple(actual, expected, prefix)
        both_model = is_model_dump_object(actual) and is_model_dump_object(expected)
        both_attrs = is_attrs_instance(actual) and is_attrs_instance(expected)
        if both_model or both_attrs:
            return self.fields(actual, expected, prefix, both_model=both_model)
        if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
            return self.sequence(actual, expected, prefix)
        return None

    def mapping(self, actual, expected, prefix: _Path) -> Iterator[_Frame] | None:
        """The walk over two mappings, or ``None`` when either cannot be walked by key.

        Both sides are snapshotted first, so the keys walked below are the ones that were proved readable
        rather than a second reading of a value free to answer differently between passes.
        """
        kept, kept_expected = keyed_snapshot(actual), keyed_snapshot(expected)
        if kept is None or kept_expected is None:
            return None
        actual_keys = set(kept)
        expected_keys = set(kept_expected)
        self.entries.extend(_order_entries(actual, expected, kept, kept_expected, prefix))
        keyed = keyed_names(kept, kept_expected)
        if self.config is not None and self.config.strict_types:
            # `{True} & {1}` hands back whichever side the set drew from, losing the type that differs
            stored = {key: key for key in kept_expected}
            for key in kept:
                found, counterpart = lookup(stored, key)
                counterpart = counterpart if found else key
                if type(key) is not type(counterpart):
                    self.entries.append(prefix.key(key).entry(actual=key, expected=counterpart))
        return self.keys(kept, kept_expected, actual_keys, expected_keys, keyed, prefix)

    def keys(self, kept, kept_expected, actual_keys, expected_keys, keyed, prefix: _Path) -> Iterator[_Frame]:
        """The children of two snapshotted mappings, key by key in the order a reader wrote them."""
        for key in _ordered_keys(kept, kept_expected):
            # the side that holds an equal key under another object is read by that object, which no lookup compares
            in_expected, expected_key = held_key(expected_keys, key)
            in_actual, actual_key = held_key(actual_keys, key)
            if not in_expected:
                self.entries.append(prefix.key(key).entry(actual=kept[key], expected=None, absent="expected"))
            elif not in_actual:
                self.entries.append(prefix.key(key).entry(actual=None, absent="actual", expected=kept_expected[key]))
            else:
                decision = (
                    _node_decision(*keyed_pair(kept, kept_expected, key), self.config, field=key)
                    if key in keyed
                    else _node_decision(kept[actual_key], kept_expected[expected_key], self.config, field=key)
                )
                if decision == "leaf":
                    path = prefix.key(key)
                    self.entries.append(path.entry(actual=kept[actual_key], expected=kept_expected[expected_key]))
                elif decision != "equal":
                    frame = self.descend(kept[actual_key], kept_expected[expected_key], prefix.key(key), decision)
                    if frame is not None:
                        yield frame

    def dataclass(self, actual, expected, prefix: _Path) -> Iterator[_Frame]:
        """The children of two dataclasses, over both sides' field names in declaration order.

        A field present on one side only is reported as absent from the other.  Shared by the top-level
        and nested ladders, so both report dataclass fields identically.
        """
        # a field declared `compare=False` is outside the dataclass's own `==`, so it stays outside here
        actual_names = [field.name for field in dataclasses.fields(actual) if field.compare]
        expected_names = [field.name for field in dataclasses.fields(expected) if field.compare]
        in_actual, in_expected = set(actual_names), set(expected_names)
        for field in _ordered_keys(actual_names, expected_names):
            if field not in in_expected:
                self.entries.append(
                    prefix.attr(field).entry(actual=getattr(actual, field), expected=None, absent="expected")
                )
            elif field not in in_actual:
                self.entries.append(
                    prefix.attr(field).entry(actual=None, absent="actual", expected=getattr(expected, field))
                )
            else:
                actual_value = getattr(actual, field)
                expected_value = getattr(expected, field)
                decision = _node_decision(actual_value, expected_value, self.config, field=field)
                if decision == "leaf":
                    self.entries.append(prefix.attr(field).entry(actual=actual_value, expected=expected_value))
                elif decision != "equal":
                    frame = self.descend(actual_value, expected_value, prefix.attr(field), decision)
                    if frame is not None:
                        yield frame

    def namedtuple(self, actual, expected, prefix: _Path) -> Iterator[_Frame]:
        """The children of two namedtuples, field by field, a field one side lacks reported as absent."""
        for field in actual._fields:
            actual_value = getattr(actual, field)
            # `_fields` and not `getattr`: a field named like a tuple method resolves to the method, not to absent
            if field not in expected._fields:
                self.entries.append(prefix.attr(field).entry(actual=actual_value, expected=None, absent="expected"))
            else:
                expected_value = getattr(expected, field)
                decision = _node_decision(actual_value, expected_value, self.config, field=field)
                if decision == "leaf":
                    self.entries.append(prefix.attr(field).entry(actual=actual_value, expected=expected_value))
                elif decision != "equal":
                    frame = self.descend(actual_value, expected_value, prefix.attr(field), decision)
                    if frame is not None:
                        yield frame
        self.entries.extend(
            prefix.attr(field).entry(actual=None, absent="actual", expected=getattr(expected, field))
            for field in expected._fields
            if field not in actual._fields
        )

    def fields(self, actual, expected, prefix: _Path, *, both_model: bool) -> Iterator[_Frame]:
        """The children of two pydantic-style models or two attrs instances, field by field."""
        actual_dict, expected_dict = _field_dict(actual, both_model), _field_dict(expected, both_model)
        keyed = keyed_names(actual_dict, expected_dict)
        for key in _ordered_keys(actual_dict, expected_dict):
            if key not in expected_dict:
                self.entries.append(prefix.attr(key).entry(actual=actual_dict[key], expected=None, absent="expected"))
            elif key not in actual_dict:
                self.entries.append(prefix.attr(key).entry(actual=None, absent="actual", expected=expected_dict[key]))
            else:
                decision = (
                    _node_decision(*keyed_pair(actual_dict, expected_dict, key), self.config, field=key)
                    if key in keyed
                    else _node_decision(actual_dict[key], expected_dict[key], self.config, field=key)
                )
                if decision == "leaf":
                    self.entries.append(prefix.attr(key).entry(actual=actual_dict[key], expected=expected_dict[key]))
                elif decision != "equal":
                    frame = self.descend(actual_dict[key], expected_dict[key], prefix.attr(key), decision)
                    if frame is not None:
                        yield frame

    def sequence(self, actual, expected, prefix: _Path) -> Iterator[_Frame]:
        """The children of two sequences, paired by alignment where that reads shorter.

        An element inserted or removed shifts everything after it, and pairing by index then calls every
        later element different.  Pairing by `difflib` alignment reports the one insertion instead.
        Shared by the top-level and nested ladders, so both decompose sequences identically.  Elements have
        no field name, so a ``config`` applies only type comparators and tolerance to them.

        The walk over the children is handed to the driver itself rather than delegated to, so a `StopIteration`
        of the value's own that the walk turns into `RuntimeError` reaches `_escaped_stop()` with no frame between.
        """
        actual, expected = readable(actual), readable(expected)
        opcodes = _alignment_opcodes_if_useful(actual, expected)
        if opcodes is not None:
            return self.aligned(actual, expected, prefix, opcodes)
        return self.positional(actual, expected, prefix)

    def positional(self, actual, expected, prefix: _Path) -> Iterator[_Frame]:
        """The children of two sequences paired by index."""
        max_len = max(len(actual), len(expected))
        for i in range(max_len):
            if i >= len(actual):
                self.entries.append(prefix.index(i).entry(actual=None, absent="actual", expected=expected[i]))
            elif i >= len(expected):
                self.entries.append(prefix.index(i).entry(actual=actual[i], expected=None, absent="expected"))
            else:
                # the path is built after the decision: an empty list per equal element cost 15% of the walk
                decision = _node_decision(actual[i], expected[i], self.config)
                if decision == "leaf":
                    self.entries.append(prefix.index(i).entry(actual=actual[i], expected=expected[i]))
                elif decision != "equal":
                    frame = self.descend(actual[i], expected[i], prefix.index(i), decision)
                    if frame is not None:
                        yield frame

    def aligned(self, actual, expected, prefix: _Path, opcodes) -> Iterator[_Frame]:
        """The children of a pair the alignment reports as shifted.

        A one-sided entry names the sequence its index belongs to (``actual[2]``, ``expected[1]``).  Once
        the two sides have shifted apart their index spaces no longer agree, and numbering both as ``[i]``
        put two unrelated entries on one path - the reader cannot tell which sequence the number indexes,
        and a consumer reading entries by path sees a collision.
        """
        for tag, actual_start, actual_stop, expected_start, expected_stop in opcodes:
            if tag == "equal" and self.config is None:
                continue  # `_alignment_opcodes()` holds these equal, the whole test when no config narrows it
            for offset in range(max(actual_stop - actual_start, expected_stop - expected_start)):
                actual_index, expected_index = actual_start + offset, expected_start + offset
                if actual_index >= actual_stop:
                    path = prefix.side_index("expected", expected_index)
                    self.entries.append(path.entry(actual=None, absent="actual", expected=expected[expected_index]))
                elif expected_index >= expected_stop:
                    path = prefix.side_index("actual", actual_index)
                    self.entries.append(path.entry(actual=actual[actual_index], expected=None, absent="expected"))
                else:
                    actual_item, expected_item = actual[actual_index], expected[expected_index]
                    decision = _node_decision(actual_item, expected_item, self.config)
                    if decision == "leaf":
                        path = prefix.index(actual_index)
                        self.entries.append(path.entry(actual=actual_item, expected=expected_item))
                    elif decision != "equal":
                        frame = self.descend(actual_item, expected_item, prefix.index(actual_index), decision)
                        if frame is not None:
                            yield frame


def _build_equality_diff(
    actual: object, expected: object, *, _prefix: _Path = _ROOT, _seen: set[int] | None = None, config=None
) -> DiffResult:
    walk = _Walk(config, () if _seen is None else _seen)
    left, right = id(actual), id(expected)
    if left in walk.on_path or right in walk.on_path:
        return DiffResult(
            kind="scalar",
            entries=[_prefix.leaf_entry(actual="<circular ref>", expected="<circular ref>")],
        )
    walk.on_path[left] = actual
    walk.on_path[right] = expected

    strict_descent = False
    if config is not None:
        # the root, where identity does not stand in for equality
        decision = _node_decision(actual, expected, config, at_root=_prefix is _ROOT)
        if decision == "equal":
            return DiffResult(kind="scalar", entries=[])
        if decision == "leaf":
            return DiffResult(kind="scalar", entries=[_prefix.leaf_entry(actual=actual, expected=expected)])
        strict_descent = decision == "strict"

    if is_namedtuple(actual) and is_namedtuple(expected):
        return DiffResult(kind="namedtuple", entries=walk.run(walk.namedtuple(actual, expected, _prefix), left, right))
    if (
        dataclasses.is_dataclass(actual)
        and not isinstance(actual, type)
        and dataclasses.is_dataclass(expected)
        and not isinstance(expected, type)
    ):
        return DiffResult(kind="dataclass", entries=walk.run(walk.dataclass(actual, expected, _prefix), left, right))
    both_model = is_model_dump_object(actual) and is_model_dump_object(expected)
    both_attrs = is_attrs_instance(actual) and is_attrs_instance(expected)
    if both_model or both_attrs:
        fields = walk.fields(actual, expected, _prefix, both_model=both_model)
        return DiffResult(kind="model" if both_model else "attrs", entries=walk.run(fields, left, right))
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return DiffResult(kind="sequence", entries=walk.run(walk.sequence(actual, expected, _prefix), left, right))
    if isinstance(actual, (set, frozenset)) and isinstance(expected, (set, frozenset)):
        entries = [
            _prefix.member(item, "extra").entry(actual=item, expected=None, absent="expected")
            for item in sorted((item for item in actual if not member(item, expected)), key=_safe_repr)
        ]
        entries.extend(
            _prefix.member(item, "missing").entry(actual=None, absent="actual", expected=item)
            for item in sorted((item for item in expected if not member(item, actual)), key=_safe_repr)
        )
        return DiffResult(kind="set", entries=entries)
    # under a strict descent this means the two sides were already equal, not that they differ
    if strict_descent:
        return DiffResult(kind="scalar", entries=[])
    # bytes render as `b'...'`, which difflib points into like text, and both expose `splitlines()`
    both_text = isinstance(actual, str) and isinstance(expected, str)
    both_bytes = isinstance(actual, (bytes, bytearray)) and isinstance(expected, (bytes, bytearray))
    if both_text or both_bytes:
        entries = []
        actual_lines = actual.splitlines()
        expected_lines = expected.splitlines()
        max_len = max(len(actual_lines), len(expected_lines))
        for i in range(max_len):
            if i >= len(actual_lines):
                entries.append(_prefix.line(i + 1).entry(actual=None, absent="actual", expected=expected_lines[i]))
            elif i >= len(expected_lines):
                entries.append(_prefix.line(i + 1).entry(actual=actual_lines[i], expected=None, absent="expected"))
            elif actual_lines[i] != expected_lines[i]:
                entries.append(_prefix.line(i + 1).entry(actual=actual_lines[i], expected=expected_lines[i]))
        if not entries:
            entries.append(DiffEntry(path=".", actual=actual, expected=expected))
        return DiffResult(kind="string", entries=entries)
    return DiffResult(kind="scalar", entries=[_prefix.leaf_entry(actual=actual, expected=expected)])


def _sub_diff_entries(
    actual: object, expected: object, prefix: _Path = _ROOT, *, _seen: set[int] | None = None, config=None
) -> list[DiffEntry] | None:
    """Canonical recursive diff for a value, returning path-level entries (or ``None`` for a leaf).

    Recurses into mappings, dataclasses, namedtuples, model-dump objects and sequences, returning a
    (possibly empty) list for those; anything else returns ``None`` so the caller renders a single
    leaf entry.  The empty-list-vs-``None`` distinction lets a caller tell a recursable value whose
    children are all ``config``-tolerated (empty list, no entry) from a genuinely differing leaf
    (``None``, one entry).  This is the single nested engine shared by the top-level paths:
    `_build_equality_diff()` (lists, dataclasses, ...) and the dict path
    (`HelpersMixin._dict_err()`), which calls it with an empty ``prefix`` so the top-level dict
    keys render bare (``b``) and nested keys render dotted (``u.b``).
    """
    walk = _Walk(config, () if _seen is None else _seen)
    if id(actual) in walk.on_path or id(expected) in walk.on_path:
        return [prefix.entry(actual="<circular ref>", expected="<circular ref>")]
    frame = walk.opened(actual, expected, prefix)
    return None if frame is None else walk.run(*frame)


def _walk_leaves(value, prefix: _Path = _ROOT) -> Iterator[tuple[_Path, object]]:
    """Yield ``(path, leaf)`` for every scalar leaf of an object graph, depth-first.

    Recurses into the same containers as the rich-diff engine (`_sub_diff_entries()`): mappings,
    dataclasses, namedtuples, model-dump objects, attrs instances, lists and tuples.  Anything else -
    scalars, strings, sets, opaque objects - is yielded as a single leaf, so the paths match the diffs.
    A circular reference yields one ``(path, "<circular ref>")`` leaf and stops, mirroring the cycle guard.

    A field of the value itself is named bare (``age``) where the diff walkers name it ``.age``: these
    paths go into a message about the fields of the value under test, not into a diff between two of them.

    Walked on a list of iterators with the ancestors held by id, as `_Walk` is and for the same reasons.  An
    exception, or the walk being closed, closes the iterators still open innermost first, as leaving nested
    calls would have: an iterator of the value's own runs its cleanup before the caller sees the error.
    """
    on_path: dict[int, object] = {}
    root = ((part, prefix) for part in (value,))
    stack: list[tuple[Generator[tuple[object, _Path], None, None], int | None]] = [(root, None)]
    try:
        while stack:
            parts, owner = stack[-1]
            for part, path in parts:
                if type(part) in _EQ_ATOMIC:
                    yield (path, part)
                    continue
                if id(part) in on_path:
                    yield (path, "<circular ref>")
                    continue
                inner = _leaf_parts(part, path)
                if inner is None:
                    yield (path, part)
                    continue
                on_path[id(part)] = part
                stack.append((inner, id(part)))
                break
            else:
                stack.pop()
                if owner is not None:
                    del on_path[owner]
    except BaseException:
        for parts, _ in reversed(stack):
            parts.close()
        raise


def _leaf_parts(value, prefix: _Path) -> Generator[tuple[object, _Path], None, None] | None:
    """The parts `_walk_leaves()` goes on into, each with its path, or ``None`` for a leaf."""
    if is_mapping_like(value):
        return ((value[key], prefix.key(key)) for key in value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _named_parts(value, dataclasses.fields(value), prefix, _field_name)
    if is_namedtuple(value):
        return _named_parts(value, value._fields, prefix, lambda name: name)
    if is_model_dump_object(value):
        held = model_field_values(value)
        return ((held[key], prefix.attr(str(key), dotted_at_root=False)) for key in held)
    if is_attrs_instance(value):
        return _named_parts(value, value.__attrs_attrs__, prefix, _field_name)
    if isinstance(value, (list, tuple)):
        return ((item, prefix.index(index)) for index, item in enumerate(value))
    return None


def _named_parts(
    value, fields: Iterable[Any], prefix: _Path, name_of: Callable[[Any], str]
) -> Generator[tuple[object, _Path], None, None]:
    """Each field of *value* with its path, the name read for the path and read again for the value, as ever."""
    for field in fields:
        path = prefix.attr(name_of(field), dotted_at_root=False)
        yield getattr(value, name_of(field)), path


def _field_name(field: Any) -> str:
    return field.name


def run_nested(walk: Generator[Any, Any, _T]) -> _T:
    """Run a recursive walk written as a generator, which yields each nested walk it needs and is sent its result.

    The nested walks wait on a list rather than on the interpreter's stack, so a value as deep as Python itself
    compares is walked, where a call per level ran into the recursion limit first.  An exception closes the
    walks it leaves, innermost first, as returning through calls would have: an iterator of the value's own that
    a walk holds runs its cleanup before the caller sees the error.
    """
    stack: list[Generator[Any, Any, Any]] = [walk]
    answer: Any = None
    try:
        while True:
            try:
                nested = stack[-1].send(answer)
            except StopIteration as done:
                stack.pop()
                if not stack:
                    return done.value
                answer = done.value
                continue
            except RuntimeError as error:
                escaped = _escaped_stop(error)
                if escaped is None:
                    raise
            else:
                stack.append(nested)
                answer = None
                continue
            raise escaped
    except BaseException:
        for pending in reversed(stack):
            pending.close()
        raise


def _escaped_stop(error: RuntimeError) -> StopIteration | None:
    """The `StopIteration` a walk's own frame turned into *error*, to be raised as it was, or ``None``.

    A `StopIteration` leaving a generator becomes a `RuntimeError`, where the same call in a plain function let it
    through, and the walks were plain functions.  Turned by the walk itself, the error's traceback holds only the
    frame that resumed it; turned deeper, by a generator of the value's own, it passed through the walk's frame and
    was a `RuntimeError` then too.
    """
    cause = error.__cause__
    trace = error.__traceback__
    if isinstance(cause, StopIteration) and trace is not None and trace.tb_next is None:
        return cause
    return None
