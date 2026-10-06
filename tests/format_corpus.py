"""Texts near a `uri`, a `hostname` and a `duration`, for the checks of `conforms_to_openapi` to be compared on.

One corpus for two comparisons: with the packages jsonschema asks for each format, and with the grammar of the
format written out a second time.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


def near(base: list[str], parts: list[list[str]]) -> Iterator[str]:
    """Every text that differs from *base* in at most two of its parts, each part taken from its choices.

    A text of many random parts is refused for all of them at once, which shows nothing.  One or two parts
    away from a valid text is where a grammar and a package can part.
    """
    for first, second in itertools.combinations(range(len(parts)), 2):
        for one, other in itertools.product(parts[first], parts[second]):
            yield "".join([*base[:first], one, *base[first + 1 : second], other, *base[second + 1 :]])


_COUNTS = ["", "1", "0", "12", "007", "1.5", "-1", "1e2", "\u0661"]


def durations() -> Iterator[str]:
    units = [[count + unit if count else "" for count in _COUNTS] + [unit] for unit in "YMDWHMS"]
    parts = [["P", "p", "", "-P", "+P"], *units[:4], ["T", "t", ""], *units[4:], ["", " ", "\n", "T"]]
    for base in ("P 1Y 2M 3D - T 4H 5M 6S -", "P - - - 1W - - - - -", "P - - 3D - - - - - -", "P - - - - T - 5M - -"):
        yield from near([part.replace("-", "") for part in base.split()], parts)


_LABELS = ["a", "A1", "0", "a-b", "a--b", "xn--nxasmq6b", "x" * 63, "-a", "a-", "a_b", "x" * 64, "", "\u00e9", "a b"]


def hostnames() -> Iterator[str]:
    later = ["", *["." + label for label in _LABELS]]
    parts = [["", ".", " "], _LABELS, later, later, ["", ".", "\n", " "]]
    for base in (["", "a", ".b", ".c", ""], ["", "A1", "", "", ""], ["", "x" * 63, "." + "x" * 63, "", ""]):
        yield from near(base, parts)
    longest = ".".join(["x" * 63] * 3)
    yield from (f"{longest}.{'x' * last}{end}" for last in (60, 61, 62, 63) for end in ("", ".", "\n"))


def in_brackets() -> list[str]:
    """Hosts in brackets one group away from an IPv6 address: asked of `ipaddress` here, of a pattern there."""
    groups = [
        "",
        "0",
        "0001",
        "FFFF",
        "12345",
        "g",
        "1.2.3.4",
        "01.2.3.4",
        "1.02.3.4",
        "1.2.3.04",
        "256.1.1.1",
        "1.2.3",
    ]
    found = []
    for address in ("::1", "2001:db8::7", "1:2:3:4:5:6:7:8", "::ffff:1.2.3.4", "1:2:3:4:5:6:1.2.3.4", "::", "1::"):
        held = address.split(":")
        for index, group in itertools.product(range(len(held)), groups):
            found.append("[" + ":".join([*held[:index], group, *held[index + 1 :]]) + "]")
            found.append("[" + ":".join([*held[:index], group, *held[index:]]) + "]")
    return found


def uris() -> Iterator[str]:
    scheme = ["http", "urn", "a+b-c.d", "HTTP", "1a", "a_b", "", "\u00e9"]
    colon = [":", "", "::"]
    user = ["//", "//user@", "//u:p@", "//u%41@", "//@", "//u%4@", "//[@", "//a b@", "//u@@"]
    host = ["example.com", "[2001:db8::7]", "", "a%41.b", "1.2.3.4", "999.1.1.1", "[v1.x]", "[v.x]", "[::1", "::1]"]
    host += ["[fe80::1%25eth0]", "ex ample", "ex^ample", "\u00e9.com", "[::1]x", *in_brackets()]
    port = ["", ":80", ":", ":99999999", ":abc", ":8a", ":-1"]
    path = [
        "/a/b",
        "",
        "/",
        "/a//b",
        "/%41",
        "/a:b@c",
        "/~_-.!$&'()*+,;=",
        "//a",
        "/%4",
        "/a b",
        "/a^b",
        "/[",
        "/\u00e9",
    ]
    rootless = ["a", "a/b", "a:b", "+1-816", "%41", "a b", "%", "[", *path]
    query = ["", "?a=b&c=/?", "?", "?%41", "?a#b", "?%", "?a b", "?[", "?a^"]
    fragment = ["", "#a/?", "#", "#%41", "#%", "#a b", "#a#b", "#["]
    end = ["", "\n", " "]
    with_a_host = [scheme, colon, user, host, port, path, query, fragment, end]
    yield from near(["http", ":", "//", "example.com", "", "/a/b", "", "", ""], with_a_host)
    yield from near(["urn", ":", "//u:p@", "[2001:db8::7]", ":80", "", "?a=b&c=/?", "#a/?", ""], with_a_host)
    yield from near(["urn", ":", "a", "", "", ""], [scheme, colon, rootless, query, fragment, end])
