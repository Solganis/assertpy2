"""Guards the one failure mode an assertion library must never have: passing without asserting.

A green test that checked nothing is worse than a red one, because nobody goes looking for it. Two
shapes of that bug are reachable here. An assertion can be handed no arguments to check against, and
a quantifier can be handed an empty subject. The first has nothing to assert and must be refused. The
second is true by definition, so it stays allowed and is pinned below as a deliberate contract rather
than left as an accident that a rewrite could flip in silence.
"""

import inspect

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from assertpy2 import assert_that


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
