"""Maximum pairing between two sides, for every assertion that says "these each, in any order"."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

__tracebackhide__ = True


def maximum_pairing(candidates: Sequence[set[int]]) -> dict[int, int]:
    """As many entries paired with distinct options as can be, returned as ``{option: entry}``.

    Kuhn's algorithm: every entry takes a free option first, and each one left over then tries to
    displace an owner along a chain of alternatives.
    """
    paired: dict[int, int] = {}
    unpaired = []
    for entry, options in enumerate(candidates):
        free = next((index for index in options if index not in paired), None)
        if free is None:
            unpaired.append(entry)
        else:
            paired[free] = entry
    for entry in unpaired:
        _augmented(entry, candidates, paired)
    return paired


def _augmented(entry: int, candidates: Sequence[set[int]], paired: dict[int, int]) -> bool:
    """Whether one entry can be paired by displacing others, updating `paired` when it can.

    Iterative, because the chain of displacements is as long as the input is wide rather than as deep:
    1100 entries against 1100 options every one of them accepts recursed past the limit and reported a
    `RecursionError` for a pairing that exists.
    """
    seen: set[int] = set()
    path: list[tuple[int, Iterator[int]]] = [(entry, iter(candidates[entry]))]
    taken: list[int] = []
    while path:
        options = path[-1][1]
        for index in options:
            if index in seen:
                continue
            seen.add(index)
            taken.append(index)
            if index not in paired:
                for step, (displaced, _) in reversed(list(enumerate(path))):
                    paired[taken[step]] = displaced
                return True
            path.append((paired[index], iter(candidates[paired[index]])))
            break
        else:
            path.pop()
            if taken:
                taken.pop()
    return False
