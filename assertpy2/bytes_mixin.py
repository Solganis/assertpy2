from __future__ import annotations

from typing import TYPE_CHECKING

from ._mixin_base import _MixinBase

if TYPE_CHECKING:
    from typing_extensions import Self

__tracebackhide__ = True


class BytesMixin(_MixinBase):
    """Assertions for bytes and bytearray values."""

    def _check_bytes(self) -> None:
        if not isinstance(self.val, (bytes, bytearray)):
            raise TypeError("val is not bytes or bytearray")

    def is_valid_utf8(self) -> Self:
        """Assert that val is valid UTF-8.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is not valid UTF-8
        """
        self._check_bytes()
        try:
            self.val.decode("utf-8")
        except UnicodeDecodeError:
            return self.error("Expected valid UTF-8, but decoding failed.")
        return self

    def is_valid_encoding(self, encoding: str) -> Self:
        """Assert that val is valid in the given encoding.

        Args:
            encoding: the encoding to validate against (e.g. ``"ascii"``, ``"utf-16"``).

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val cannot be decoded with the given encoding
        """
        self._check_bytes()
        try:
            self.val.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            return self.error(f"Expected valid {encoding} encoding, but decoding failed.")
        return self

    def starts_with_bytes(self, prefix: bytes) -> Self:
        """Assert that val starts with the given byte prefix.

        Args:
            prefix: the expected byte prefix.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not start with the prefix
        """
        self._check_bytes()
        if not self.val.startswith(prefix):
            return self.error(f"Expected to start with <{prefix!r}>, but did not.")
        return self

    def contains_bytes(self, sub: bytes) -> Self:
        """Assert that val contains the given byte subsequence.

        Args:
            sub: the byte subsequence to find.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not contain the subsequence
        """
        self._check_bytes()
        if sub not in self.val:
            return self.error(f"Expected to contain <{sub!r}>, but did not.")
        return self

    def has_byte_at(self, index: int, expected: int) -> Self:
        """Assert that the byte at the given index equals the expected value.

        Args:
            index: zero-based byte index.
            expected: expected byte value (0-255).

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the byte at index does not match
        """
        self._check_bytes()
        if index < 0 or index >= len(self.val):
            raise IndexError(f"Expected index {index} to be in range [0, {len(self.val)}), but was out of range.")
        actual = self.val[index]
        if actual != expected:
            return self.error(f"Expected byte at index {index} to be <0x{expected:02x}>, but was <0x{actual:02x}>.")
        return self

    def is_hex_equal_to(self, expected_hex: str) -> Self:
        """Assert that val equals the given hex string.

        Args:
            expected_hex: hex string without prefix (e.g. ``"abcdef"``).

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not match the hex string
        """
        self._check_bytes()
        expected = bytes.fromhex(expected_hex)
        if self.val != expected:
            return self.error(f"Expected hex <{expected_hex}>, but was <{self.val.hex()}>.")
        return self

    def decoded_as(self, encoding: str = "utf-8") -> Self:
        """Decode val and return a new builder with the decoded string.

        Args:
            encoding: the encoding to use (default ``"utf-8"``).

        Returns:
            AssertionBuilder: a new instance with the decoded string as val

        Raises:
            UnicodeDecodeError: if val cannot be decoded
        """
        self._check_bytes()
        decoded = self.val.decode(encoding)
        return self.builder(decoded, self.description, self.kind)
