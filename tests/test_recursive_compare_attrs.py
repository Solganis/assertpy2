import pytest

pytest.importorskip("attrs", reason="attrs not installed")

import attrs

from assertpy2 import assert_that
from assertpy2.helpers import HelpersMixin


@attrs.define
class Product:
    sku: str
    name: str
    price: float


@attrs.define
class Order:
    id: int
    product: Product
    quantity: int


class TestAttrsIgnore:
    def test_ignore_field(self):
        actual = Product(sku="ABC", name="Widget", price=9.99)
        expected = Product(sku="XYZ", name="Widget", price=9.99)
        assert_that(actual).is_equal_to(expected, ignore="sku")

    def test_include_field(self):
        actual = Product(sku="ABC", name="Widget", price=9.99)
        expected = Product(sku="XYZ", name="Widget", price=0.01)
        assert_that(actual).is_equal_to(expected, include="name")

    def test_nested_attrs_ignore(self):
        actual = Order(id=1, product=Product(sku="A", name="W", price=10.0), quantity=5)
        expected = Order(id=99, product=Product(sku="A", name="W", price=10.0), quantity=5)
        assert_that(actual).is_equal_to(expected, ignore="id")


class TestAttrsListOfObjects:
    def test_list_of_attrs_ignore(self):
        actual = [Product(sku="A", name="W1", price=10.0), Product(sku="B", name="W2", price=20.0)]
        expected = [Product(sku="X", name="W1", price=10.0), Product(sku="Y", name="W2", price=20.0)]
        assert_that(actual).is_equal_to(expected, ignore="sku")


class TestAttrsToComparableDict:
    def test_attrs(self):
        product = Product(sku="A", name="W", price=10.0)
        result = HelpersMixin._to_comparable_dict(product)
        assert result == {"sku": "A", "name": "W", "price": 10.0}
