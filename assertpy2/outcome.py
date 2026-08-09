"""The record of one failed assertion, between composing it and doing something about it.

`AssertionBuilder.error()` used to do both jobs in one body: it built the message, and then it decided
whether to raise, collect or log.  Only the string survived that function, which is why the soft
collector can hold nothing else, why there is nowhere to hand a caller a result instead of an
exception, and why `eventually()` has to bypass `error()` entirely to attach its poll trace.

Splitting the two leaves a record in the middle.  This is that record.  It carries what was composed,
not what should happen to it: the decision belongs to the delivery half, which reads the builder's
mode.

Deliberately not exported yet.  It grows a field per phase as something starts reading it, and
publishing a shape that is still moving would be a promise this cannot keep.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .errors import DiffResult


@dataclass(frozen=True, slots=True, kw_only=True)
class AssertionOutcome:
    """One composed failure, before it is raised, collected or logged."""

    message: str
    """The full text, description prefix and all, exactly as it reaches the reader."""

    actual: object = None
    expected: object = None
    diff: DiffResult | None = None

    hint: str | None = None
    """The diagnostic line, kept apart from ``message`` as well as glued into it.

    It is glued in because that is where a reader needs it, and kept apart because once it is part of
    the string nothing downstream can tell it from the assertion's own words.
    """
