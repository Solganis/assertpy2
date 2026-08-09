"""Setup the guide pages assume a reader already has, kept out of the rendered page.

Source text rather than objects because both guards read it: ``test_docs_typing`` prepends it to the
snippet it type-checks, ``test_docs_examples`` executes it into the namespace it runs the block in.
Two definitions would let a fixture satisfy one guard and not the other.

Being listed here does not put a page in both guards. ``docs/concepts/type-safety.md`` is checked
statically only, and its fixture says so by raising from every body.
"""

from __future__ import annotations

TYPE_SAFETY = '''
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


repo = _Repo()
response = _Response()
order = PaidOrder()
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

PAGE_FIXTURES = {
    "docs/concepts/type-safety.md": TYPE_SAFETY,
    "docs/guides/fluent.md": FLUENT,
    "docs/guides/testing.md": TESTING,
}
