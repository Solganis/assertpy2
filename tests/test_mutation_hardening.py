"""Tests added to close real gaps surfaced by mutation testing (cosmic-ray).

Each test exercises a previously-untested behavior (a boundary, an operator direction, or a
negative case) that allowed an equivalent-looking mutant to survive. Grouped here by module
for review; can be redistributed into the per-feature test files later.
"""

import pytest

from assertpy2 import assert_that, match

# --- matchers ---


def test_is_zero_matcher_rejects_negative():
    assert_that(match.is_zero().matches(-5)).is_false()  # `== 0` -> `<= 0` would wrongly match


def test_is_odd_matcher_uses_modulo_not_bitand():
    assert_that(match.is_odd().matches(5)).is_true()  # `% 2` -> `& 2` would say 5 is not odd


def test_is_divisible_by_matcher_allows_negative_divisor():
    assert_that(match.is_divisible_by(-3).matches(9)).is_true()
    assert_that(match.is_divisible_by(-3).matches(10)).is_false()  # `== 0` -> `<= 0` would match


def test_close_to_matcher_boundary_and_operator():
    assert_that(match.close_to(10, 2).matches(12)).is_true()  # exactly at edge; `<=` -> `<` fails it
    assert_that(match.close_to(10, 2).matches(20)).is_false()  # `-` -> `%` would match (20 % 10 == 0)


def test_matches_structure_value_less_than_expected():
    with pytest.raises(AssertionError):
        assert_that({"n": 3}).matches_structure({"n": 5})  # `!=` -> `>` would pass


# --- numeric / range boundaries ---


def test_is_between_allows_equal_low_and_high():
    assert_that(5).is_between(5, 5)  # `low > high` -> `>=` would raise on equal bounds


def test_is_close_to_allows_zero_tolerance():
    assert_that(5).is_close_to(5, 0)  # `tolerance < 0` -> `<= 0` would reject exact tolerance


# --- dict ---


def test_contains_entry_rejects_empty_entry():
    with pytest.raises(ValueError):
        assert_that({"a": 1}).contains_entry({})  # `len(entry) != 1` -> `> 1` would accept {}


def test_contains_entry_value_greater_than_expected():
    with pytest.raises(AssertionError):
        assert_that({"a": 5}).contains_entry({"a": 3})  # `!=` -> `<` would pass


# --- bytes ---


def test_has_byte_at_out_of_range_uses_explicit_message():
    with pytest.raises(IndexError, match="to be in range"):
        assert_that(b"abc").has_byte_at(5, 0x00)  # `>= len` -> `== len`/`> len` falls to raw IndexError


def test_has_byte_at_value_greater_than_expected():
    with pytest.raises(AssertionError):
        assert_that(b"\xff").has_byte_at(0, 0x01)  # `!=` -> `<` would pass


def test_is_hex_equal_to_value_greater_than_expected():
    with pytest.raises(AssertionError):
        assert_that(b"\xff").is_hex_equal_to("00")  # `!=` -> `<` would pass


# --- collection ---


def test_element_out_of_range_uses_explicit_message():
    with pytest.raises(IndexError, match="to be in range"):
        assert_that([1, 2, 3]).element(5)  # `>= len` -> `== len`/`> len` falls to raw IndexError


def test_single_rejects_two_elements():
    with pytest.raises(ValueError):
        assert_that([1, 2]).single()  # `> 1` -> `> 2` would silently take the first of two


# --- string ---


def test_is_equal_to_ignoring_case_lexicographically_less():
    with pytest.raises(AssertionError):
        assert_that("ABC").is_equal_to_ignoring_case("xyz")  # `!=` -> `>` would pass ("abc" < "xyz")


# --- base ---


def test_is_length_actual_longer_than_expected():
    with pytest.raises(AssertionError):
        assert_that([1, 2, 3]).is_length(2)  # `!=` -> `<` would pass when actual is longer
