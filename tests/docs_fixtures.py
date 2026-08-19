"""Setup the guide pages assume a reader already has, kept out of the rendered page.

Source text rather than objects because both guards read it: ``test_docs_typing`` prepends it to the
snippet it type-checks, ``test_docs_examples`` executes it into the namespace it runs the block in.
Two definitions would let a fixture satisfy one guard and not the other.

Being listed here does not put a page in both guards. ``docs/concepts/type-safety.md`` is checked
statically only, and its fixture says so by raising from every body.
"""

from __future__ import annotations

import pathlib


def documented_pages(excluded: dict[str, str]) -> list[str]:
    """Every markdown page a guard should read, minus the ones excluded with a reason.

    A glob rather than a hand-kept list, so a page added tomorrow is guarded by default and has to be
    excluded deliberately.  The two lists this replaced drifted apart and neither said why: three pages
    carrying fourteen code blocks were outside both, including the one whose central example does not
    type-check.  Failing closed costs an exclusion entry; failing open costs a page nobody checks.
    """
    pages = ["README.md", *sorted(path.as_posix() for path in pathlib.Path("docs").rglob("*.md"))]
    stale = sorted(set(excluded) - set(pages))
    if stale:
        # a renamed page would otherwise leave its exclusion behind, excusing nothing while reading as
        # though the decision still stood, and the renamed page itself would rejoin the guard unnoticed
        raise ValueError(f"excluded pages that no longer exist: {stale}")
    return [page for page in pages if page not in excluded]


TYPE_SAFETY = '''
from datetime import date
from typing import Any

from pydantic import BaseModel
from typing_extensions import TypeIs


class OrderModel(BaseModel):
    id: int
    total: float


class Order:
    """The reader's own domain class, as the surrounding prose describes it."""

    total: float
    status: str


class PaidOrder(Order):
    def refund(self) -> None:
        raise NotImplementedError


class _Repo:
    def find_order(self, order_id: int) -> Order | None:
        raise NotImplementedError

    def all_orders(self) -> list[Order]:
        raise NotImplementedError


class _Response:
    def json(self) -> Any:
        raise NotImplementedError


# what the page's counter-examples are written about: a class answering to nothing the library can
# use, which is the one kind of value the narrowed fallback applies to
class Person:
    def __init__(self, first_name: str) -> None:
        self.first_name = first_name


repo = _Repo()
response = _Response()
order = PaidOrder()
person = Person("Fred")
'''

# Every value here is chosen to make the page's own assertions hold: `users` has exactly the five
# active rows the page filters down to, `orders` the one FAILED row it maps and reads the first of.
FLUENT = """
from dataclasses import dataclass, field


@dataclass
class _Person:
    first_name: str = ""
    last_name: str = ""
    shoe_size: int = 0
    name: str = ""
    tags: list[str] = field(default_factory=list)
    active: bool = True


@dataclass
class _Order:
    status: str
    total: float


fred = _Person(first_name="Fred", last_name="Smith", shoe_size=12, name="Fred Smith")
people = [
    _Person(first_name="Fred", name="Fred Smith"),
    _Person(first_name="Joe", name="Joe Bloggs"),
]
users = [
    _Person(name="Alice", tags=["admin"]),
    _Person(name="Bob", tags=["user"]),
    _Person(name="Carol", tags=["user"]),
    _Person(name="Dave", tags=["admin"]),
    _Person(name="Erin", tags=["user"]),
]
items = [1, -2, 3, -4]
orders = [_Order(status="FAILED", total=19.99), _Order(status="PAID", total=5.0)]
"""

# Static only, like TYPE_SAFETY: the page's own examples write snapshot files, and a guard that ran
# them would leave those files behind in the repo.
TESTING = """
from typing import Any

import pytest


class _HttpResponse:
    def json(self) -> Any:
        raise NotImplementedError


class _Client:
    def get(self, url: str) -> _HttpResponse:
        raise NotImplementedError


def get_status() -> str:
    raise NotImplementedError


async def async_get_status() -> str:
    raise NotImplementedError


def get_name() -> str:
    raise NotImplementedError


def get_count() -> int:
    raise NotImplementedError


def get_order() -> Any:
    raise NotImplementedError


def load(name: str) -> Any:
    raise NotImplementedError


client = _Client()
headers = {"Content-Type": "application/json"}
body = {"status": "ok"}
x, y, z = 1, "value", [1, 2, 3]
order: dict[str, Any] = {}
response = _HttpResponse()
api_response: dict[str, Any] = {}
payload: dict[str, Any] = {}
metrics: dict[str, float] = {}
"""

# The page registers `is_5` in its first block and keeps using it in later ones, which each guard reads
# on its own. `some_library` stands for whatever the reader is wrapping, so it is stubbed to the shape
# the example uses rather than dropped: a block nobody checks is how the `is_5` gap went unnoticed.
EXTENDING = """
class _ValidationError(Exception):
    pass


class _SomeLibrary:
    ValidationError = _ValidationError

    def validate(self, value: object) -> None:
        raise NotImplementedError


some_library = _SomeLibrary()


def is_5(self):
    if self.val != 5:
        return self.error(f"{self.val} is NOT 5!")
    return self
"""

# behave is not installed in the guard's environment (it changes the failure path for the whole suite,
# so it gets its own CI job), and the step decorators are the only thing the page borrows from it.
INTEGRATIONS = """
from typing import Any

import numpy as np
import pandas as pd


def given(text: str) -> Any:
    raise NotImplementedError


def when(text: str) -> Any:
    raise NotImplementedError


actual = pd.DataFrame({"a": [1, 2]})
expected = pd.DataFrame({"a": [1, 2]})
computed = np.array([1.0, 2.0])
"""

PAGE_FIXTURES = {
    "docs/concepts/type-safety.md": TYPE_SAFETY,
    "docs/guides/fluent.md": FLUENT,
    "docs/guides/testing.md": TESTING,
    "docs/extending/custom-assertions.md": EXTENDING,
    "docs/extending/integrations.md": INTEGRATIONS,
}
