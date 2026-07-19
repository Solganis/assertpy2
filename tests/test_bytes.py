import pytest

from assertpy2 import assert_that, soft_assertions


class TestIsValidUtf8:
    def test_valid_utf8(self):
        assert_that(b"hello").is_valid_utf8()

    def test_valid_utf8_with_multibyte(self):
        assert_that("привет".encode()).is_valid_utf8()

    def test_invalid_utf8(self):
        with pytest.raises(AssertionError, match="valid UTF-8"):
            assert_that(b"\xff\xfe").is_valid_utf8()

    def test_bytearray(self):
        assert_that(bytearray(b"hello")).is_valid_utf8()

    def test_non_bytes_raises(self):
        with pytest.raises(TypeError, match="not bytes"):
            assert_that("string").is_valid_utf8()


class TestIsValidEncoding:
    def test_valid_ascii(self):
        assert_that(b"hello").is_valid_encoding("ascii")

    def test_invalid_ascii(self):
        with pytest.raises(AssertionError, match="ascii"):
            assert_that("привет".encode()).is_valid_encoding("ascii")

    def test_valid_latin1(self):
        assert_that(b"\xe4\xf6\xfc").is_valid_encoding("latin-1")

    def test_invalid_encoding_name(self):
        with pytest.raises(AssertionError, match="decoding failed"):
            assert_that(b"hello").is_valid_encoding("nonexistent-encoding")

    def test_non_bytes_raises(self):
        with pytest.raises(TypeError, match="not bytes"):
            assert_that(42).is_valid_encoding("utf-8")


class TestStartsWithBytes:
    def test_match(self):
        assert_that(b"\x89PNG\r\n").starts_with_bytes(b"\x89PNG")

    def test_no_match(self):
        with pytest.raises(AssertionError, match="start with"):
            assert_that(b"hello").starts_with_bytes(b"world")

    def test_empty_prefix(self):
        assert_that(b"hello").starts_with_bytes(b"")

    def test_non_bytes_raises(self):
        with pytest.raises(TypeError, match="not bytes"):
            assert_that("hello").starts_with_bytes(b"h")


class TestContainsBytes:
    def test_match(self):
        assert_that(b"hello world").contains_bytes(b"world")

    def test_no_match(self):
        with pytest.raises(AssertionError, match="to contain"):
            assert_that(b"hello").contains_bytes(b"\x00\x01")

    def test_single_byte(self):
        assert_that(b"\x00\x01\x02").contains_bytes(b"\x01")

    def test_non_bytes_raises(self):
        with pytest.raises(TypeError, match="not bytes"):
            assert_that(42).contains_bytes(b"\x00")


class TestHasByteAt:
    def test_match(self):
        assert_that(b"\x89PNG").has_byte_at(0, 0x89)

    def test_no_match(self):
        with pytest.raises(AssertionError, match="0x50"):
            assert_that(b"\x89PNG").has_byte_at(1, 0x51)

    def test_out_of_range(self):
        with pytest.raises(IndexError, match="out of range"):
            assert_that(b"ab").has_byte_at(5, 0x00)

    def test_negative_index(self):
        with pytest.raises(IndexError, match="out of range"):
            assert_that(b"ab").has_byte_at(-1, 0x00)

    def test_non_bytes_raises(self):
        with pytest.raises(TypeError, match="not bytes"):
            assert_that(42).has_byte_at(0, 0x00)


class TestIsHexEqualTo:
    def test_match(self):
        assert_that(b"\xab\xcd\xef").is_hex_equal_to("abcdef")

    def test_no_match(self):
        with pytest.raises(AssertionError, match="hex"):
            assert_that(b"\xab\xcd").is_hex_equal_to("abce")

    def test_uppercase_hex(self):
        assert_that(b"\xab\xcd").is_hex_equal_to("ABCD")

    def test_non_bytes_raises(self):
        with pytest.raises(TypeError, match="not bytes"):
            assert_that("hello").is_hex_equal_to("68656c6c6f")


class TestDecodedAs:
    def test_utf8(self):
        assert_that(b"hello").decoded_as("utf-8").is_equal_to("hello")

    def test_default_encoding(self):
        assert_that(b"hello").decoded_as().is_equal_to("hello")

    def test_latin1(self):
        assert_that(b"\xe4\xf6\xfc").decoded_as("latin-1").is_equal_to("\xe4\xf6\xfc")

    def test_chaining(self):
        assert_that(b"HTTP/1.1 200").decoded_as().starts_with("HTTP").contains("200")

    def test_invalid_decode_raises(self):
        with pytest.raises(UnicodeDecodeError):
            assert_that(b"\xff\xfe").decoded_as("ascii")

    def test_preserves_description(self):
        result = assert_that(b"hello").described_as("raw").decoded_as()
        assert_that(result.description).is_equal_to("raw")

    def test_non_bytes_raises(self):
        with pytest.raises(TypeError, match="not bytes"):
            assert_that(42).decoded_as()


class TestBytesSoftMode:
    def test_soft_assertions(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(b"\xff").is_valid_utf8()
            assert_that(b"hello").starts_with_bytes(b"world")
        msg = str(exc_info.value)
        assert_that(msg).contains("1.")
        assert_that(msg).contains("2.")


class TestBytesBoundaryCases:
    """Boundary and operator-direction cases for the bytes assertions."""

    def test_has_byte_at_index_equal_to_length_raises_range_error(self):
        with pytest.raises(IndexError, match="to be in range"):
            assert_that(b"abc").has_byte_at(3, 0)  # index equal to length

    def test_has_byte_at_index_beyond_length_raises_range_error(self):
        with pytest.raises(IndexError, match="to be in range"):
            assert_that(b"abc").has_byte_at(5, 0)  # index past the end

    def test_has_byte_at_actual_greater_than_expected_fails(self):
        with pytest.raises(AssertionError):
            assert_that(b"\xff").has_byte_at(0, 0x01)

    def test_is_hex_equal_to_actual_greater_than_expected_fails(self):
        with pytest.raises(AssertionError):
            assert_that(b"\xff").is_hex_equal_to("01")


def test_bytes_equality_failure_points_at_the_changed_span():
    # bytes render as their b'...' literal, so difflib can point into them the way it does for text
    with pytest.raises(AssertionError) as exc_info:
        assert_that(b"hello world payload").is_equal_to(b"hello WORLD payload")
    diff = exc_info.value.diff
    assert_that(diff.kind).is_equal_to("string")
    assert_that(diff.entries).is_length(1)
    assert_that(diff.entries[0].actual).is_equal_to(b"hello world payload")
    assert_that(diff.entries[0].expected).is_equal_to(b"hello WORLD payload")


def test_bytearray_equality_failure_uses_the_same_path():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(bytearray(b"abc")).is_equal_to(bytearray(b"aXc"))
    assert_that(exc_info.value.diff.kind).is_equal_to("string")


def test_bytes_against_str_is_not_treated_as_text():
    # different types, so the text path must not claim them
    with pytest.raises(AssertionError) as exc_info:
        assert_that(b"abc").is_equal_to("abc")
    assert_that(exc_info.value.diff.kind).is_equal_to("scalar")
