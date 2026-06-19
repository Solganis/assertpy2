from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ._mixin_base import _MixinBase

if TYPE_CHECKING:
    from ._compat import Self

__tracebackhide__ = True


def contents_of(file, encoding="utf-8"):
    """Helper to read the contents of the given file or path into a string with the given encoding.

    Args:
        file: a *path-like object* (aka a file name) or a *file-like object* (aka a file)
        encoding (str): the target encoding.  Defaults to ``utf-8``, other useful encodings are ``ascii`` and ``latin-1``.

    Examples:
        Usage::

            from assertpy2 import assert_that, contents_of

            contents = contents_of('foo.txt')
            assert_that(contents).starts_with('foo').ends_with('bar').contains('oob')

    Returns:
        str: returns the file contents as a string

    Raises:
        IOError: if file not found
        TypeError: if file is not a *path-like object* or a *file-like object*
    """
    try:
        contents = file.read()
    except AttributeError:
        try:
            with open(file) as fp:
                contents = fp.read()
        except TypeError:
            raise ValueError(f"val must be file or path, but was type <{type(file).__name__}>") from None
        except OSError:
            if not isinstance(file, (str, os.PathLike)):
                raise ValueError(f"val must be file or path, but was type <{type(file).__name__}>") from None
            raise

    if isinstance(contents, (bytes, bytearray)):
        return contents.decode(encoding, "replace")
    return contents


class FileMixin(_MixinBase):
    """File assertions mixin."""

    def exists(self) -> Self:
        """Asserts that val is a path and that it exists.

        Examples:
            Usage::

                assert_that('myfile.txt').exists()
                assert_that('mydir').exists()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist
        """
        if not isinstance(self.val, (str, os.PathLike)):
            raise TypeError("val is not a path")
        if not os.path.exists(self.val):
            return self.error(f"Expected <{self.val}> to exist, but was not found.")
        return self

    def does_not_exist(self) -> Self:
        """Asserts that val is a path and that it does *not* exist.

        Examples:
            Usage::

                assert_that('missing.txt').does_not_exist()
                assert_that('missing_dir').does_not_exist()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** exist
        """
        if not isinstance(self.val, (str, os.PathLike)):
            raise TypeError("val is not a path")
        if os.path.exists(self.val):
            return self.error(f"Expected <{self.val}> to not exist, but was found.")
        return self

    def is_file(self) -> Self:
        """Asserts that val is a *file* and that it exists.

        Examples:
            Usage::

                assert_that('myfile.txt').is_file()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** a file
        """
        self.exists()
        if not os.path.isfile(self.val):
            return self.error(f"Expected <{self.val}> to be a file, but was not.")
        return self

    def is_directory(self) -> Self:
        """Asserts that val is a *directory* and that it exists.

        Examples:
            Usage::

                assert_that('mydir').is_directory()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** a directory
        """
        self.exists()
        if not os.path.isdir(self.val):
            return self.error(f"Expected <{self.val}> to be a directory, but was not.")
        return self

    def is_named(self, filename) -> Self:
        """Asserts that val is an existing path to a file and that file is named filename.

        Args:
            filename: the expected filename

        Examples:
            Usage::

                assert_that('/path/to/mydir/myfile.txt').is_named('myfile.txt')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** a file, or is **not** named the given filename
        """
        self.is_file()
        if not isinstance(filename, (str, os.PathLike)):
            raise TypeError("given filename arg must be a path")
        val_filename = os.path.basename(os.path.abspath(self.val))
        if val_filename != filename:
            return self.error(f"Expected filename <{val_filename}> to be equal to <{filename}>, but was not.")
        return self

    def is_child_of(self, parent) -> Self:
        """Asserts that val is an existing path to a file and that file is a child of parent.

        Args:
            parent: the expected parent directory

        Examples:
            Usage::

                assert_that('/path/to/mydir/myfile.txt').is_child_of('mydir')
                assert_that('/path/to/mydir/myfile.txt').is_child_of('to')
                assert_that('/path/to/mydir/myfile.txt').is_child_of('path')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** a file, or is **not** a child of the given directory
        """
        self.is_file()
        if not isinstance(parent, (str, os.PathLike)):
            raise TypeError("given parent directory arg must be a path")
        val_abspath = os.path.abspath(self.val)
        parent_abspath = os.path.abspath(parent)
        if not val_abspath.startswith(parent_abspath):
            return self.error(f"Expected file <{val_abspath}> to be a child of <{parent_abspath}>, but was not.")
        return self

    def is_readable(self) -> Self:
        """Asserts that val is an existing path and is readable.

        Examples:
            Usage::

                assert_that('/path/to/file.txt').is_readable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** readable
        """
        self.exists()
        if not os.access(self.val, os.R_OK):
            return self.error(f"Expected <{self.val}> to be readable, but was not.")
        return self

    def is_writable(self) -> Self:
        """Asserts that val is an existing path and is writable.

        Examples:
            Usage::

                assert_that('/path/to/file.txt').is_writable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** writable
        """
        self.exists()
        if not os.access(self.val, os.W_OK):
            return self.error(f"Expected <{self.val}> to be writable, but was not.")
        return self

    def is_executable(self) -> Self:
        """Asserts that val is an existing path and is executable.

        Examples:
            Usage::

                assert_that('/path/to/script.sh').is_executable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** executable
        """
        self.exists()
        if not os.access(self.val, os.X_OK):
            return self.error(f"Expected <{self.val}> to be executable, but was not.")
        return self
