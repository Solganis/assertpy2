import pytest

from assertpy2 import assert_that, match
from assertpy2.matchers import (
    EachMatcher,
    IgnoreMatcher,
    IsNonEmptyStringMatcher,
    IsUuidMatcher,
    StructureMatcher,
)


class TestIgnoreMatcher:
    def test_matches_anything(self):
        m = match.ignore()
        assert_that(m.matches(None)).is_true()
        assert_that(m.matches(42)).is_true()
        assert_that(m.matches("hello")).is_true()
        assert_that(m.matches([1, 2, 3])).is_true()
        assert_that(m.matches({})).is_true()

    def test_describe(self):
        assert_that(match.ignore().describe()).is_equal_to("anything (ignored)")

    def test_is_instance(self):
        assert_that(match.ignore()).is_instance_of(IgnoreMatcher)


class TestIsUuidMatcher:
    def test_matches_valid_uuid4(self):
        assert_that(match.is_uuid().matches("550e8400-e29b-41d4-a716-446655440000")).is_true()

    def test_matches_valid_uuid1(self):
        assert_that(match.is_uuid().matches("6ba7b810-9dad-11d1-80b4-00c04fd430c8")).is_true()

    def test_does_not_match_invalid(self):
        assert_that(match.is_uuid().matches("not-a-uuid")).is_false()

    def test_does_not_match_empty(self):
        assert_that(match.is_uuid().matches("")).is_false()

    def test_does_not_match_non_string(self):
        assert_that(match.is_uuid().matches(42)).is_false()
        assert_that(match.is_uuid().matches(None)).is_false()

    def test_describe(self):
        assert_that(match.is_uuid().describe()).is_equal_to("a valid UUID string")

    def test_is_instance(self):
        assert_that(match.is_uuid()).is_instance_of(IsUuidMatcher)


class TestIsNonEmptyStringMatcher:
    def test_matches_non_empty(self):
        assert_that(match.is_non_empty_string().matches("hello")).is_true()
        assert_that(match.is_non_empty_string().matches(" ")).is_true()

    def test_does_not_match_empty(self):
        assert_that(match.is_non_empty_string().matches("")).is_false()

    def test_does_not_match_non_string(self):
        assert_that(match.is_non_empty_string().matches(42)).is_false()
        assert_that(match.is_non_empty_string().matches(None)).is_false()
        assert_that(match.is_non_empty_string().matches(["a"])).is_false()

    def test_describe(self):
        assert_that(match.is_non_empty_string().describe()).is_equal_to("a non-empty string")

    def test_is_instance(self):
        assert_that(match.is_non_empty_string()).is_instance_of(IsNonEmptyStringMatcher)


class TestEachMatcher:
    def test_all_match(self):
        m = match.each_item(match.is_positive())
        assert_that(m.matches([1, 2, 3])).is_true()

    def test_some_do_not_match(self):
        m = match.each_item(match.is_positive())
        assert_that(m.matches([1, -2, 3])).is_false()

    def test_empty_iterable(self):
        m = match.each_item(match.is_positive())
        assert_that(m.matches([])).is_true()

    def test_non_iterable(self):
        m = match.each_item(match.is_positive())
        assert_that(m.matches(42)).is_false()

    def test_describe(self):
        m = match.each_item(match.is_positive())
        assert_that(m.describe()).is_equal_to("each item matching a positive value")

    def test_describe_mismatch_with_failing_item(self):
        m = match.each_item(match.is_positive())
        result = m.describe_mismatch([1, -2, 3])
        assert_that(result).contains("index 1")
        assert_that(result).contains("-2")

    def test_describe_mismatch_non_iterable(self):
        m = match.each_item(match.is_positive())
        result = m.describe_mismatch(42)
        assert_that(result).contains("not iterable")

    def test_is_instance(self):
        assert_that(match.each_item(match.is_positive())).is_instance_of(EachMatcher)

    def test_composition(self):
        m = match.each_item(match.between(1, 10) & match.is_instance_of(int))
        assert_that(m.matches([1, 5, 10])).is_true()
        assert_that(m.matches([1, 5, 11])).is_false()

    def test_describe_mismatch_all_match(self):
        m = match.each_item(match.is_positive())
        assert_that(m.describe_mismatch([1, 2, 3])).is_equal_to("was <[1, 2, 3]>")


class TestStructureMatcher:
    def test_basic_match(self):
        m = match.structure({"name": match.is_non_empty_string(), "age": match.is_positive()})
        assert_that(m.matches({"name": "Alice", "age": 30})).is_true()

    def test_missing_key(self):
        m = match.structure({"name": match.is_non_empty_string(), "age": match.is_positive()})
        assert_that(m.matches({"name": "Alice"})).is_false()

    def test_value_mismatch(self):
        m = match.structure({"age": match.is_positive()})
        assert_that(m.matches({"age": -1})).is_false()

    def test_extra_keys_allowed(self):
        m = match.structure({"name": match.is_non_empty_string()})
        assert_that(m.matches({"name": "Alice", "extra": "field"})).is_true()

    def test_raw_value_equality(self):
        m = match.structure({"status": "active", "count": 5})
        assert_that(m.matches({"status": "active", "count": 5})).is_true()
        assert_that(m.matches({"status": "inactive", "count": 5})).is_false()

    def test_nested_dict(self):
        m = match.structure({"user": {"name": match.is_non_empty_string(), "role": "admin"}})
        assert_that(m.matches({"user": {"name": "Alice", "role": "admin"}})).is_true()
        assert_that(m.matches({"user": {"name": "Alice", "role": "user"}})).is_false()

    def test_nested_not_dict(self):
        m = match.structure({"user": {"name": match.is_non_empty_string()}})
        assert_that(m.matches({"user": "not a dict"})).is_false()

    def test_non_dict_value(self):
        m = match.structure({"a": 1})
        assert_that(m.matches("not a dict")).is_false()
        assert_that(m.matches(42)).is_false()
        assert_that(m.matches(None)).is_false()

    def test_describe(self):
        m = match.structure({"name": match.is_non_empty_string(), "age": 30})
        desc = m.describe()
        assert_that(desc).contains("name: a non-empty string")
        assert_that(desc).contains("age: <30>")

    def test_describe_nested(self):
        m = match.structure({"user": {"name": match.is_non_empty_string()}})
        desc = m.describe()
        assert_that(desc).contains("user: {name: a non-empty string}")

    def test_describe_mismatch_missing_key(self):
        m = match.structure({"name": match.is_non_empty_string()})
        result = m.describe_mismatch({"age": 30})
        assert_that(result).contains("missing key <name>")

    def test_describe_mismatch_value_fail(self):
        m = match.structure({"age": match.is_positive()})
        result = m.describe_mismatch({"age": -1})
        assert_that(result).contains("at <age>")
        assert_that(result).contains("a positive value")

    def test_describe_mismatch_non_dict(self):
        m = match.structure({"a": 1})
        result = m.describe_mismatch("not a dict")
        assert_that(result).contains("was not a dict")

    def test_describe_mismatch_nested_path(self):
        m = match.structure({"user": {"name": match.is_non_empty_string()}})
        result = m.describe_mismatch({"user": {"name": ""}})
        assert_that(result).contains("user.name")

    def test_is_instance(self):
        assert_that(match.structure({"a": 1})).is_instance_of(StructureMatcher)

    def test_with_ignore(self):
        m = match.structure({"id": match.ignore(), "name": match.is_non_empty_string()})
        assert_that(m.matches({"id": 12345, "name": "Alice"})).is_true()
        assert_that(m.matches({"id": None, "name": "Bob"})).is_true()

    def test_with_uuid(self):
        m = match.structure({"id": match.is_uuid()})
        assert_that(m.matches({"id": "550e8400-e29b-41d4-a716-446655440000"})).is_true()
        assert_that(m.matches({"id": "not-uuid"})).is_false()

    def test_with_each_item(self):
        m = match.structure({"scores": match.each_item(match.between(0, 100))})
        assert_that(m.matches({"scores": [85, 90, 78]})).is_true()
        assert_that(m.matches({"scores": [85, 101, 78]})).is_false()

    def test_deeply_nested(self):
        m = match.structure({"a": {"b": {"c": match.equal_to(42)}}})
        assert_that(m.matches({"a": {"b": {"c": 42}}})).is_true()
        assert_that(m.matches({"a": {"b": {"c": 99}}})).is_false()

    def test_describe_mismatch_raw_value(self):
        m = match.structure({"status": "active"})
        result = m.describe_mismatch({"status": "inactive"})
        assert_that(result).contains("at <status>")
        assert_that(result).contains("expected <active>")
        assert_that(result).contains("was <inactive>")

    def test_describe_mismatch_all_match(self):
        m = match.structure({"a": 1})
        assert_that(m.describe_mismatch({"a": 1})).is_equal_to("was <{'a': 1}>")


class TestMatchesStructureMethod:
    def test_basic(self):
        user = {"name": "Alice", "age": 30}
        assert_that(user).matches_structure({"name": match.is_non_empty_string(), "age": match.between(18, 120)})

    def test_failure_missing_key(self):
        with pytest.raises(AssertionError, match="missing key"):
            assert_that({"name": "Alice"}).matches_structure(
                {"name": match.is_non_empty_string(), "email": match.is_non_empty_string()}
            )

    def test_failure_value_mismatch(self):
        with pytest.raises(AssertionError, match="at <age>"):
            assert_that({"age": -5}).matches_structure({"age": match.is_positive()})

    def test_nested(self):
        data = {"user": {"name": "Alice", "settings": {"theme": "dark"}}}
        assert_that(data).matches_structure(
            {"user": {"name": match.is_non_empty_string(), "settings": {"theme": "dark"}}}
        )

    def test_non_dict_val(self):
        with pytest.raises(TypeError, match="val must be a dict"):
            assert_that("not a dict").matches_structure({"a": 1})

    def test_non_dict_spec(self):
        with pytest.raises(TypeError, match="given arg must be a dict"):
            assert_that({"a": 1}).matches_structure("not a dict")

    def test_chaining(self):
        data = {"name": "Alice", "age": 30}
        assert_that(data).matches_structure({"name": match.is_non_empty_string()}).contains_key("age")

    def test_with_uuid_and_ignore(self):
        response = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "created_at": "2024-01-01T00:00:00Z",
            "name": "Test",
        }
        assert_that(response).matches_structure(
            {
                "id": match.is_uuid(),
                "created_at": match.ignore(),
                "name": match.equal_to("Test"),
            }
        )

    def test_error_message_contains_structure_description(self):
        with pytest.raises(AssertionError, match="to match structure"):
            assert_that({"x": 1}).matches_structure({"x": match.is_non_empty_string()})
