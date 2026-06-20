import pytest

pytest.importorskip("pydantic", reason="pydantic not installed")

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel

from assertpy2 import assert_that


class UserDto(BaseModel):
    id: int
    name: str


class UserDtoWithEmail(BaseModel):
    id: int
    name: str
    email: str


class AddressDto(BaseModel):
    city: str
    zip_code: str


class UserDtoWithAddress(BaseModel):
    id: int
    name: str
    address: AddressDto


class TestPydanticIgnore:
    def test_ignore_field(self):
        actual = UserDto(id=1, name="Alice")
        expected = UserDto(id=99, name="Alice")
        assert_that(actual).is_equal_to(expected, ignore="id")

    def test_nested_model_ignore(self):
        actual = UserDtoWithAddress(id=1, name="Alice", address=AddressDto(city="NYC", zip_code="10001"))
        expected = UserDtoWithAddress(id=1, name="Alice", address=AddressDto(city="NYC", zip_code="99999"))
        assert_that(actual).is_equal_to(expected, ignore=[("address", "zip_code")])


class TestPydanticInclude:
    def test_include_field(self):
        actual = UserDtoWithEmail(id=1, name="Alice", email="a@x.com")
        expected = UserDtoWithEmail(id=99, name="Alice", email="different@x.com")
        assert_that(actual).is_equal_to(expected, include="name")


class TestPydanticListOfObjects:
    def test_list_of_pydantic_ignore(self):
        actual = [UserDto(id=1, name="Alice"), UserDto(id=2, name="Bob")]
        expected = [UserDto(id=99, name="Alice"), UserDto(id=99, name="Bob")]
        assert_that(actual).is_equal_to(expected, ignore="id")


_addresses = st.builds(AddressDto, city=st.text(max_size=5), zip_code=st.text(max_size=5))
_users = st.builds(UserDtoWithAddress, id=st.integers(), name=st.text(max_size=5), address=_addresses)


class TestPydanticProperties:
    @settings(deadline=None)
    @given(left=_users, right=_users)
    def test_is_equal_to_consistent_with_eq(self, left, right):
        if left == right:
            assert_that(left).is_equal_to(right)
        else:
            with pytest.raises(AssertionError):
                assert_that(left).is_equal_to(right)

    @settings(deadline=None)
    @given(value=_users)
    def test_is_equal_to_reflexive(self, value):
        assert_that(value).is_equal_to(value.model_copy(deep=True))

    @settings(deadline=None)
    @given(value=st.builds(UserDto, id=st.integers(), name=st.text(max_size=5)), new_id=st.integers())
    def test_ignore_removes_field_difference(self, value, new_id):
        other = value.model_copy(update={"id": new_id})
        assert_that(value).is_equal_to(other, ignore="id")
