"""The parts that are deliberately dynamic, used the way the documentation says to use them.

`has_*` resolves through `__getattr__`, matchers are registered at runtime, and `add_extension` adds a
method that no protocol declares.  All three are documented holes in the typed surface, so what this
project checks is that they still *work*, and that nothing in the typed part broke reaching them.
"""

from __future__ import annotations

from typing import Any

from assertpy2 import (
    BaseMatcher,
    assert_that,
    register_matcher,
    unregister_matcher,
)


class Account:
    def __init__(self, owner: str, balance: float) -> None:
        self.owner = owner
        self.balance = balance

    def is_overdrawn(self) -> bool:
        return self.balance < 0


def test_dynamic_attribute_assertions_read_the_object() -> None:
    account = Account("alice", 120.0)
    assert_that(account).has_owner("alice")
    assert_that(account).has_balance(120.0)


def test_dynamic_assertions_reach_a_zero_argument_method() -> None:
    assert_that(Account("bob", -5.0)).has_is_overdrawn(True)


class StartsWithVowel(BaseMatcher):
    """The matcher a typed consumer writes: a `BaseMatcher` subclass, which is what registration takes."""

    def matches(self, value: Any) -> bool:
        return isinstance(value, str) and value[:1].lower() in "aeiou"

    def describe(self) -> str:
        return "a word starting with a vowel"

    def describe_mismatch(self, value: Any) -> str:
        return f"<{value}> does not start with a vowel"


def test_a_registered_matcher_is_usable_by_name() -> None:
    register_matcher("starts_with_vowel")(StartsWithVowel)
    try:
        assert_that("alice").satisfies(StartsWithVowel())
        assert_that("bob").not_.satisfies(StartsWithVowel())
    finally:
        unregister_matcher("starts_with_vowel")


def test_the_negated_branch_still_answers() -> None:
    assert_that("alice").not_.is_empty()
    assert_that([1, 2]).not_.contains(3)
