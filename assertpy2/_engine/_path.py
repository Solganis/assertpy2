"""Where a diff entry sits, in both the forms its two readers need.

`DiffEntry.path` is written for a person and is lossy on purpose: a mapping key goes through ``str()``,
so ``{3: ...}`` and ``{"3": ...}`` land on the same text, and a key holding a dot or a bracket cannot be
read back out.  That is the right trade for a message and the wrong one for anything that wants to walk
back into the value, which is what `DiffEntry.steps` is for.

Both forms are carried by one object so they cannot drift.  Nine producers build paths, and each of them
would otherwise have written the text and the steps separately, twice, in agreement only by hand.

The rendering rules are **not** uniform across producers and are not made uniform here.  A mapping key
renders bare at the root (``b``) while a field renders dotted (``.b``), because a top-level dict is
reported by `HelpersMixin._dict_err()` with bare keys and has been since before this file existed.
Each hop keeps its own rule, in one place, instead of at 35 call sites.

Building a path is deferred to the point where an entry is actually produced.  The walkers used to
format one per child before deciding whether the child differed, so a sequence of a thousand equal
elements paid for a thousand strings nobody read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..errors import DiffEntry, Step, _safe_str

__tracebackhide__ = True


@dataclass(frozen=True, slots=True)
class _Path:
    """A location inside a compared value, as rendered text plus the steps that reached it.

    Not a `NamedTuple`, though it is a pair: ``index`` and ``count`` are already taken by ``tuple``, and
    a hop named ``index`` is the one this is used for most.  It was tried, and it measured the same.
    """

    text: str = ""
    steps: tuple[Step, ...] = ()

    def key(self, key: object) -> _Path:
        """Into a mapping.  Bare at the root, dotted below it, and the key itself is kept unstringified."""
        rendered = _safe_str(key)
        return _Path(f"{self.text}.{rendered}" if self.text else rendered, (*self.steps, Step("key", key)))

    def attr(self, name: str, *, dotted_at_root: bool = True) -> _Path:
        """Into a field of a dataclass, namedtuple, attrs class or model.

        ``dotted_at_root`` is not a style knob.  The diff walkers render a root-level field as ``.name``
        and the leaf walker renders it as ``name``, and both are load-bearing: the first matches how the
        dict path has rendered nested keys since before either existed, the second feeds messages that
        name a field of the value under test.  Below the root the two agree.
        """
        text = f"{self.text}.{name}" if self.text or dotted_at_root else name
        return _Path(text, (*self.steps, Step("attr", name)))

    def index(self, index: int) -> _Path:
        """Into a position both sequences share."""
        return _Path(f"{self.text}[{index}]", (*self.steps, Step("index", index)))

    def side_index(self, side: Literal["actual", "expected"], index: int) -> _Path:
        """Into a position only one sequence has, once alignment has shifted the two apart."""
        return _Path(f"{self.text}{side}[{index}]", (*self.steps, Step("index", index, side=side)))

    def line(self, number: int) -> _Path:
        """Into one line of a text or bytes diff, numbered from 1."""
        return _Path(f"line {number}", (*self.steps, Step("line", number)))

    def member(self, item: object, label: str) -> _Path:
        """Into a member of a set, which has no position to name it by.

        The text stays the label the set renderer groups on (``extra`` / ``missing``), because a member
        has no coordinate to print.  The step carries the member itself, which is the only handle on it.
        """
        return _Path(label, (*self.steps, Step("item", item)))

    def entry(
        self,
        *,
        actual: object = None,
        expected: object = None,
        absent: Literal["actual", "expected"] | None = None,
    ) -> DiffEntry:
        """A `DiffEntry` at this location, carrying both forms of it."""
        return DiffEntry(path=self.text, steps=self.steps, actual=actual, expected=expected, absent=absent)

    def leaf_entry(
        self,
        *,
        actual: object = None,
        expected: object = None,
        absent: Literal["actual", "expected"] | None = None,
    ) -> DiffEntry:
        """A `DiffEntry` for the whole value, whose text at the root is ``.`` rather than empty."""
        return DiffEntry(path=self.text or ".", steps=self.steps, actual=actual, expected=expected, absent=absent)


_ROOT: _Path = _Path()
"""The value under comparison itself, before any hop into it."""
