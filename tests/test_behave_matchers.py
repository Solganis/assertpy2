from unittest.mock import MagicMock, patch

import pytest

from assertpy2.behave_matchers import (
    ASSERTPY_TYPES,
    _bool_like,
    _non_empty_string,
    _non_negative_int,
    _positive_float,
    _positive_int,
    register_assertpy_types,
)


class TestPositiveInt:
    def test_valid(self):
        assert _positive_int("5") == 5
        assert _positive_int("1") == 1
        assert _positive_int("999") == 999

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            _positive_int("0")

    def test_has_pattern(self):
        assert _positive_int.pattern == r"\d+"


class TestNonNegativeInt:
    def test_valid(self):
        assert _non_negative_int("0") == 0
        assert _non_negative_int("42") == 42

    def test_has_pattern(self):
        assert _non_negative_int.pattern == r"\d+"


class TestPositiveFloat:
    def test_valid(self):
        assert _positive_float("3.14") == pytest.approx(3.14)
        assert _positive_float("1") == 1.0
        assert _positive_float("0.001") == pytest.approx(0.001)

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="positive float"):
            _positive_float("0")

    def test_has_pattern(self):
        assert _positive_float.pattern == r"\d+\.?\d*"


class TestNonEmptyString:
    def test_valid(self):
        assert _non_empty_string("hello") == "hello"
        assert _non_empty_string("  padded  ") == "padded"

    def test_blank_rejected(self):
        with pytest.raises(ValueError, match="non-empty string"):
            _non_empty_string("   ")

    def test_has_pattern(self):
        assert _non_empty_string.pattern == r".+?"


class TestBoolLike:
    @pytest.mark.parametrize("text", ["true", "True", "TRUE", "yes", "Yes", "1", "on", "ON"])
    def test_truthy(self, text):
        assert _bool_like(text) is True

    @pytest.mark.parametrize("text", ["false", "False", "FALSE", "no", "No", "0", "off", "OFF"])
    def test_falsy(self, text):
        assert _bool_like(text) is False

    def test_invalid_rejected(self):
        with pytest.raises(ValueError, match="boolean-like"):
            _bool_like("maybe")

    def test_has_pattern(self):
        assert _bool_like.pattern == r"\w+"


class TestAssertpyTypesDict:
    def test_contains_all_types(self):
        assert set(ASSERTPY_TYPES) == {"PositiveInt", "NonNegativeInt", "PositiveFloat", "NonEmptyString", "BoolLike"}

    def test_values_are_callables(self):
        for name, func in ASSERTPY_TYPES.items():
            assert callable(func), f"{name} is not callable"

    def test_all_have_pattern(self):
        for name, func in ASSERTPY_TYPES.items():
            assert hasattr(func, "pattern"), f"{name} missing .pattern"


class TestRegisterAssertpyTypes:
    def test_calls_register_type(self):
        mock_register = MagicMock()
        with patch.dict("sys.modules", {"behave": MagicMock(register_type=mock_register)}):
            register_assertpy_types()
        mock_register.assert_called_once_with(**ASSERTPY_TYPES)

    def test_raises_without_behave(self):
        with (
            patch.dict("sys.modules", {"behave": None}),
            pytest.raises(ImportError, match="behave is required"),
        ):
            register_assertpy_types()
