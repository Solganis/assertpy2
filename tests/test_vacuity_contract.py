"""Guards the one failure mode an assertion library must never have: passing without asserting.

A green test that checked nothing is worse than a red one, because nobody goes looking for it. Two
shapes of that bug are reachable here. An assertion can be handed no arguments to check against, and
a quantifier can be handed an empty subject. The first has nothing to assert and must be refused. The
second is true by definition, so it stays allowed and is pinned below as a deliberate contract rather
than left as an accident that a rewrite could flip in silence.
"""

import inspect
import warnings

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from assertpy2 import VacuousAssertionWarning, _satisfies, assert_that


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
        except (TypeError, ValueError):  # C-level callables carry no introspectable signature
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
    # the counterpart that proves the rows above are a contract and not an "always passes" defect
    with pytest.raises(AssertionError):
        assert_that(subject).any_satisfy(_never)


# Only the positive half of the table above: an empty subject is the expected pass for the negatives
# ("no errors were logged" is exactly what such a test wanted), so warning there would be noise.
_POSITIVE_QUANTIFIERS = {
    name: call for name, call in _VACUOUSLY_TRUE.items() if name not in {"none_satisfy", "does_not_contain_duplicates"}
}


class TestVacuousGuard:
    """The opt-in guard that names a universal assertion which checked nothing."""

    @pytest.fixture
    def guarded(self, monkeypatch):
        monkeypatch.setattr(_satisfies, "_VACUOUS_GUARD", True)

    @pytest.mark.parametrize("call", list(_POSITIVE_QUANTIFIERS.values()), ids=list(_POSITIVE_QUANTIFIERS))
    def test_every_positive_quantifier_warns_on_an_empty_subject(self, guarded, call):
        with pytest.warns(VacuousAssertionWarning):
            call([])

    def test_the_warning_names_the_method_the_caller_used(self, guarded):
        # the guard sits in each entry point, not in the shared one they delegate to: a message saying
        # "each()" for an all_satisfy() call would send the reader to the wrong docs
        with pytest.warns(VacuousAssertionWarning, match=r"^all_satisfy\(\)"):
            assert_that([]).all_satisfy(lambda item: item > 0)

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

    def test_an_unsized_subject_is_never_drained_to_check(self, guarded):
        # a one-shot iterable has no len(): consuming it to answer the question would break the assertion
        warnings.simplefilter("error", VacuousAssertionWarning)
        assert_that(iter([])).each(lambda item: item > 0)

    def test_a_broken_len_does_not_crash_the_assertion(self, guarded):
        # the guard calls len() to decide whether to warn; a value whose __len__ raises must pass
        # through untouched, not have its error surfaced as ours (same rule as the hostile __dir__)
        class BrokenLen:
            def __len__(self):
                raise ValueError("len exploded")

            def __iter__(self):
                return iter([])

        warnings.simplefilter("error", VacuousAssertionWarning)
        assert_that(BrokenLen()).each(lambda item: item > 0)

    def test_the_guard_is_off_by_default(self):
        # a suite running filterwarnings = ["error"] must not break on upgrade
        warnings.simplefilter("error", VacuousAssertionWarning)
        assert_that([]).all_satisfy(lambda item: item > 0)
