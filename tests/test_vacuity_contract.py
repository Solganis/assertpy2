"""Guards the one failure mode an assertion library must never have: passing without asserting.

A green test that checked nothing is worse than a red one, because nobody goes looking for it. Two
shapes of that bug are reachable here. An assertion can be handed no arguments to check against, and
a quantifier can be handed an empty subject. The first has nothing to assert and must be refused. The
second is true by definition, so it stays allowed and is pinned below as a deliberate contract rather
than left as an accident that a rewrite could flip in silence.
"""

import dataclasses
import inspect
import warnings

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from assertpy2 import AssertionFailure, VacuousAssertionWarning, _satisfies, assert_that, match


def _vararg_assertions() -> list[str]:
    """Public builder methods that accept ``*args`` and require no positional argument.

    Discovered by introspection rather than listed, so an assertion added tomorrow is covered without
    anyone remembering to extend a table.
    """
    builder = assert_that([])
    found = []
    for name in sorted(name for name in dir(type(builder)) if not name.startswith("_")):
        method = getattr(builder, name, None)
        if not callable(method):
            continue
        try:
            parameters = list(inspect.signature(method).parameters.values())
        except (TypeError, ValueError):
            continue
        if not any(param.kind is param.VAR_POSITIONAL for param in parameters):
            continue
        required = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        if any(param.kind in required and param.default is inspect.Parameter.empty for param in parameters):
            continue
        found.append(name)
    return found


_VARARG_ASSERTIONS = _vararg_assertions()
_SUBJECTS = st.sampled_from([[1, 2, 3], (1, 2), {"a": 1}, "abc", {1, 2}, b"ab", 42, None])


def test_the_vararg_surface_is_actually_discovered():
    # without this the property below would sample an empty list and assert nothing itself
    assert_that(_VARARG_ASSERTIONS).is_not_empty()
    assert_that(_VARARG_ASSERTIONS).contains("contains", "contains_only", "contains_exactly", "is_in")


@pytest.mark.parametrize("name", _VARARG_ASSERTIONS)
@settings(deadline=None)
@given(subject=_SUBJECTS)
def test_no_vararg_assertion_passes_with_nothing_to_assert(name, subject):
    """Zero arguments means nothing to check against, so refusing is the only honest outcome.

    ``ValueError``/``TypeError`` rather than ``AssertionError``: the caller made a usage mistake, the
    subject did not fail anything.
    """
    with pytest.raises((ValueError, TypeError)):
        getattr(assert_that(subject), name)()


def _never(item: object) -> bool:
    return False


_EMPTY_SUBJECTS = [[], (), set(), ""]

# Universal quantification over an empty set is true, the way Python's own all() and AssertJ read it.
# Each row below passes on an empty subject even though its predicate can never hold.
_VACUOUSLY_TRUE = {
    "all_satisfy": lambda subject: assert_that(subject).all_satisfy(_never),
    "none_satisfy": lambda subject: assert_that(subject).none_satisfy(_never),
    "each": lambda subject: assert_that(subject).each(lambda item: item.is_positive()),
    "is_sorted": lambda subject: assert_that(subject).is_sorted(),
    "is_subset_of": lambda subject: assert_that(subject).is_subset_of(9),
    "does_not_contain_duplicates": lambda subject: assert_that(subject).does_not_contain_duplicates(),
    "zip_satisfies": lambda subject: assert_that(subject).zip_satisfies([], lambda left, right: False),
    "has_no_none_fields": lambda subject: assert_that(subject).has_no_none_fields(),
}


@pytest.mark.parametrize("subject", _EMPTY_SUBJECTS, ids=repr)
@pytest.mark.parametrize("call", list(_VACUOUSLY_TRUE.values()), ids=list(_VACUOUSLY_TRUE))
def test_universal_quantifiers_hold_vacuously_on_an_empty_subject(call, subject):
    call(subject)


@pytest.mark.parametrize("subject", _EMPTY_SUBJECTS, ids=repr)
def test_an_existential_quantifier_fails_on_an_empty_subject(subject):
    with pytest.raises(AssertionError):
        assert_that(subject).any_satisfy(_never)


# Only the positive half of the table above: an empty subject is the expected pass for the negatives
# ("no errors were logged" is exactly what such a test wanted), so warning there would be noise.
_POSITIVE_QUANTIFIERS = {
    name: call for name, call in _VACUOUSLY_TRUE.items() if name not in {"none_satisfy", "does_not_contain_duplicates"}
} | {
    # not in the table above, which runs every entry against every empty subject: `all_fields_satisfy`
    # treats a set or a string as one leaf by design, so it is vacuous only on a container that walks
    # to nothing. The guard still has to name it, which is what it is here for.
    "all_fields_satisfy": lambda subject: assert_that(subject).all_fields_satisfy(_never),
}


@dataclasses.dataclass
class _FieldPairs:
    """Walked as fields by the assertion and as pairs by anything that iterates it, like a model."""

    id: int
    name: str

    def __iter__(self):
        return iter(dataclasses.asdict(self).items())


class _EmptyNotIterable:
    """A length of zero and no way to walk it, which is what the guard used to answer from."""

    def __len__(self):
        return 0


class _SharesOneIterator:
    def __init__(self, items):
        self.items = iter(items)

    def __iter__(self):
        return self.items


class _SharesOneIteratorBehindFreshGenerators:
    def __init__(self, items):
        self.items = iter(items)

    def __iter__(self):
        return (item for item in self.items)


class TestVacuousGuard:
    """The opt-in guard that names a universal assertion which checked nothing."""

    @pytest.fixture
    def guarded(self, monkeypatch):
        monkeypatch.setattr(_satisfies, "_VACUOUS_GUARD", True)

    @pytest.mark.parametrize("call", list(_POSITIVE_QUANTIFIERS.values()), ids=list(_POSITIVE_QUANTIFIERS))
    def test_every_positive_quantifier_warns_on_an_empty_subject(self, guarded, call):
        with pytest.warns(VacuousAssertionWarning):
            call([])

    @pytest.mark.parametrize(("name", "call"), list(_POSITIVE_QUANTIFIERS.items()), ids=list(_POSITIVE_QUANTIFIERS))
    def test_the_warning_names_the_method_the_caller_used(self, guarded, name, call):
        # the guard sits in each entry point, not in the shared one they delegate to: a message saying
        # "each()" for an all_satisfy() call would send the reader to the wrong docs. Checking one
        # entry point left every other one free to pass whatever name it liked.
        with pytest.warns(VacuousAssertionWarning, match=rf"^{name}\(\)"):
            call([])

    def test_the_warning_points_at_the_caller(self, guarded):
        with pytest.warns(VacuousAssertionWarning) as caught:
            assert_that([]).all_satisfy(lambda item: item > 0)
        assert_that(caught[0].filename).ends_with("test_vacuity_contract.py")

    def test_allow_empty_is_honoured(self, guarded):
        warnings.simplefilter("error", VacuousAssertionWarning)
        assert_that([]).all_satisfy(lambda item: item > 0, allow_empty=True)
        assert_that([]).each(lambda item: item > 0, allow_empty=True)
        assert_that([]).all_fields_satisfy(lambda item: item > 0, allow_empty=True)
        assert_that([]).has_no_none_fields(allow_empty=True)
        assert_that([]).zip_satisfies([], lambda left, right: False, allow_empty=True)
        assert_that([]).is_sorted(allow_empty=True)
        assert_that([]).is_subset_of(9, allow_empty=True)

    def test_negative_quantifiers_stay_silent(self, guarded):
        warnings.simplefilter("error", VacuousAssertionWarning)
        assert_that([]).none_satisfy(_never)
        assert_that([]).does_not_contain(1)
        assert_that([]).does_not_contain_duplicates()

    def test_a_non_empty_subject_never_warns(self, guarded):
        warnings.simplefilter("error", VacuousAssertionWarning)
        assert_that([1, 2]).all_satisfy(lambda item: item > 0)
        assert_that([1, 2]).is_sorted()

    def test_a_spent_iterator_is_caught_like_any_other_empty_subject(self, guarded):
        # it has no len() to ask, and the guard used to step aside for that and let the assertion pass
        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(VacuousAssertionWarning):
            assert_that(iter([])).each(lambda item: item > 0)

    def test_looking_at_a_one_shot_subject_leaves_the_assertion_its_items(self, guarded):
        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(iter([1, -2, 3])).each(lambda item: item > 0)
        assert_that(str(exc_info.value)).contains("index 1")

    def test_the_subject_is_never_replaced_by_anything_the_guard_did(self, guarded):
        """The guard reads what the walk counted, so it has nothing to take and nothing to put back.

        An earlier design asked the subject before the walk, which meant taking one item from a
        one-shot value and handing on the continuation instead of the value.  `.value` promises the
        object handed in, and this is what holds it to that with the guard on.
        """
        warnings.simplefilter("error", VacuousAssertionWarning)
        source = iter([1, 2, 3])
        assert_that(assert_that(source).each(lambda item: item > 0).value).is_same_as(source)

    def test_a_field_walk_does_not_look_into_an_iterator(self, guarded):
        """To `all_fields_satisfy` an iterator is one opaque leaf, so it is never vacuous over one.

        Looking into it replaced the leaf the assertion was about to judge, and a predicate asking about
        the subject itself then failed with the guard on and passed with it off.
        """
        warnings.simplefilter("error", VacuousAssertionWarning)
        source = iter([1, 2])
        assert_that(source).all_fields_satisfy(lambda leaf: leaf is source)

    def test_an_empty_structure_with_no_length_is_caught(self, guarded):
        @dataclasses.dataclass
        class NoFields:
            pass

        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(VacuousAssertionWarning):
            assert_that(NoFields()).all_fields_satisfy(lambda leaf: True)

    def test_a_structure_that_refuses_to_be_walked_is_left_to_the_assertion(self, guarded):
        class Hostile:
            def model_dump(self):
                raise ValueError("dump exploded")

        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(ValueError, match="dump exploded"):
            assert_that(Hostile()).all_fields_satisfy(lambda leaf: True)

    def test_a_warning_never_arrives_in_front_of_a_verdict(self, guarded):
        """The guard runs after whatever refuses the call, so it cannot speak for a failing one."""
        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([]).zip_satisfies([1], lambda left, right: True)
        assert_that(str(exc_info.value)).contains("length")

        with pytest.raises(TypeError):
            assert_that([]).each("not a matcher")
        with pytest.raises(TypeError):
            assert_that([]).all_satisfy("not a matcher")
        with pytest.raises(ValueError, match="one or more superset"):
            assert_that([]).is_subset_of()
        with pytest.raises(TypeError, match="dict-like"):
            assert_that({}).is_subset_of("not a mapping")
        with pytest.raises(TypeError, match="iterable"):
            assert_that(_EmptyNotIterable()).all_satisfy(lambda item: True)
        with pytest.raises(TypeError, match="key"):
            assert_that([]).is_sorted(key=42)

    @pytest.mark.parametrize(
        "call",
        [
            lambda: assert_that([1, -2]).each(lambda item: item > 0),
            lambda: assert_that([1, -2]).all_satisfy(lambda item: item > 0),
            lambda: assert_that(iter([1, -2])).each(lambda item: item > 0),
            lambda: assert_that({"a": -1}).all_fields_satisfy(lambda leaf: leaf > 0),
            lambda: assert_that([2, 1]).is_sorted(),
            lambda: assert_that({"a": 1}).is_subset_of({"b": 2}),
            lambda: assert_that([1]).zip_satisfies([2], lambda left, right: left == right),
        ],
        ids=["each", "all_satisfy", "one-shot", "fields", "sorted", "subset", "zip"],
    )
    def test_turning_the_guard_on_never_changes_a_verdict(self, call):
        """The property every defect in this guard broke, asked of one call at a time.

        A diagnostic that decides differently from the assertion it watches is worse than no
        diagnostic.  Six defects were found this way after the fact; this asks the question directly.
        """
        warnings.simplefilter("ignore", VacuousAssertionWarning)
        _satisfies._VACUOUS_GUARD = False
        try:
            call()
            without = "passed"
        except Exception as refused:  # the type is the verdict being compared
            without = type(refused).__name__
        _satisfies._VACUOUS_GUARD = True
        try:
            call()
            within = "passed"
        except Exception as refused:  # the same, with the guard watching
            within = type(refused).__name__
        finally:
            _satisfies._VACUOUS_GUARD = False
        assert_that(within).described_as("the guard changed the verdict").is_equal_to(without)

    def test_a_subset_reads_its_subject_before_it_reads_a_superset(self):
        """A superset that shares the subject's iterator used to leave nothing to compare.

        The subject then counted zero and the assertion passed, whatever its values were.  Independent
        of the guard, which was right about the count and only made the emptiness audible.
        """

        class SharedKeys:
            def __init__(self, data, keys):
                self.data = data
                self.keys_iter = keys

            def keys(self):
                return self.data.keys()

            def __iter__(self):
                return self.keys_iter

            def __getitem__(self, key):
                return self.data[key]

        shared = iter(["a"])
        with pytest.raises(AssertionFailure):
            assert_that(SharedKeys({"a": 1}, shared)).is_subset_of(SharedKeys({"a": 2}, shared))

    def test_an_argument_cannot_answer_for_the_subject(self):
        """The subject is read before any argument's code runs, in both shapes this came up in."""

        class MutatingSuperset:
            def __init__(self, subject):
                self.subject = subject

            def keys(self):
                return {"a"}

            def __iter__(self):
                self.subject.data["a"] = 2
                return iter(["a"])

            def __getitem__(self, key):
                return 2

        class Subject:
            def __init__(self):
                self.data = {"a": 1}

            def keys(self):
                return self.data.keys()

            def __iter__(self):
                return iter(self.data)

            def __getitem__(self, key):
                return self.data[key]

        subject = Subject()
        with pytest.raises(AssertionFailure):
            assert_that(subject).is_subset_of(MutatingSuperset(subject))

        class MutatingLen:
            def __init__(self, other):
                self.other = other

            def __len__(self):
                self.other.append(1)
                return 2

        holder = [1]
        with pytest.raises(AssertionFailure):
            assert_that(holder).has_same_size_as(MutatingLen(holder))

    def test_an_empty_mapping_is_caught_by_the_subset_walk(self, guarded):
        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(VacuousAssertionWarning):
            assert_that({}).is_subset_of({"a": 1})

    def test_a_subject_the_guard_did_not_look_into_is_handed_on_as_it_came(self, guarded):
        warnings.simplefilter("error", VacuousAssertionWarning)
        source = [1, 2, 3]
        assert_that(assert_that(source).each(lambda item: item > 0).value).is_same_as(source)

    def test_an_endless_subject_still_stops_at_the_first_refusal(self, guarded):
        """Counting a one-shot subject to answer the guard would never return on this one."""

        def endless():
            yield 0
            while True:  # pragma: no cover - the assertion refuses the first item and never reaches here
                yield 1

        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(endless()).each(bool)
        assert_that(str(exc_info.value)).contains("index 0")

    def test_a_subject_that_can_be_walked_twice_still_sees_every_item(self, guarded):
        class Reiterable:
            def __iter__(self):
                return iter([1, -2])

        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(Reiterable()).each(lambda item: item > 0)
        assert_that(str(exc_info.value)).contains("index 1")

    @pytest.mark.parametrize(
        "subject",
        [
            lambda items: _SharesOneIterator(items),
            lambda items: _SharesOneIteratorBehindFreshGenerators(items),
        ],
        ids=["one shared iterator", "a fresh generator over shared state"],
    )
    def test_a_subject_sharing_one_position_keeps_its_items(self, guarded, subject):
        """Neither shape can be told from a re-walkable one, so the guard does not look into either.

        `iter(value) is value` says no about both, and comparing two `iter()` results tells only the
        first apart.  A version that looked anyway ate the single item each holds and the assertion
        passed green.
        """
        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(subject([0])).each(bool)
        assert_that(str(exc_info.value)).contains("index 0")

    def test_an_empty_subject_with_no_length_is_caught(self, guarded):
        class EmptyReiterable:
            def __iter__(self):
                return iter([])

        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(VacuousAssertionWarning):
            assert_that(EmptyReiterable()).each(lambda item: item > 0)

    def test_a_walked_value_is_not_replaced_by_what_the_guard_walked(self, guarded):
        model = _FieldPairs(id=-1, name="Alice")
        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(model).all_fields_satisfy(match.is_positive())
        paths = [entry.path for entry in exc_info.value.diff.entries]
        assert_that(paths).described_as("the fields, not the walk over them").is_equal_to(["id", "name"])

    def test_a_broken_len_is_beside_the_point(self, guarded):
        # the guard no longer asks for a length at all: it reads what the walk counted, so a value
        # whose `__len__` raises is answered by walking it like any other
        class BrokenLen:
            def __len__(self):
                raise ValueError("len exploded")

            def __iter__(self):
                return iter([])

        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(VacuousAssertionWarning):
            assert_that(BrokenLen()).each(lambda item: item > 0)

    def test_a_value_that_cannot_be_walked_at_all_is_left_to_the_assertion(self, guarded):
        class Hostile:
            def __iter__(self):
                raise ValueError("iteration exploded")

        warnings.simplefilter("error", VacuousAssertionWarning)
        with pytest.raises(ValueError, match="iteration exploded"):
            assert_that(Hostile()).each(lambda item: item > 0)

    def test_the_guard_is_off_by_default(self):
        warnings.simplefilter("error", VacuousAssertionWarning)
        assert_that([]).all_satisfy(lambda item: item > 0)
