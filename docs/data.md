# Data Navigation

## JSON Path / Schema

Navigate JSON structures with JSONPath and validate them against JSON Schema.

!!! note "Optional dependency"
    ```bash
    pip install assertpy2[json]
    ```

### at_json_path

Navigate to a JSONPath and keep asserting on the extracted value:

```python
data = {"users": [{"name": "Alice"}, {"name": "Bob"}], "meta": {"total": 2}}

assert_that(data).at_json_path("$.meta.total").is_equal_to(2)
assert_that(data).at_json_path("$.users[0].name").is_equal_to("Alice")
assert_that(data).at_json_path("$.users[*].name").is_equal_to(["Alice", "Bob"])
```

Raises `ValueError` if the path does not exist.

### has_json_path / does_not_have_json_path

Assert that a path is present or absent:

```python
assert_that(data).has_json_path("$.meta.total")
assert_that(data).does_not_have_json_path("$.error")
```

### matches_json_schema

Validate against a JSON Schema dict, or load it from a file:

```python
schema = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    "required": ["name"],
}

assert_that({"name": "Alice", "age": 30}).matches_json_schema(schema)
assert_that(data).matches_json_schema_from_file("schemas/user.json")
```

JSON assertions chain and work with soft assertions:

```python
with soft_assertions():
    assert_that(response).has_json_path("$.data").at_json_path("$.data.id").is_positive()
```

## Regex Group Extraction

### extracting_group()

Search the value for a pattern and continue asserting on the captured group:

```python
log = "2024-01-15 ERROR status=500 path=/api/users"

assert_that(log).extracting_group(r"status=(\d+)", 1).is_equal_to("500")        # by index
assert_that(log).extracting_group(r"(?P<level>\w+) status", "level").is_equal_to("ERROR")  # by name
assert_that("abc123").extracting_group(r"\d+").is_equal_to("123")               # group 0 = whole match
assert_that("count=42").extracting_group(r"count=(\d+)", 1).is_digit().is_length(2)  # chains
```

### matches_with_groups()

Return all groups as a tuple, or a dict for named groups:

```python
assert_that("2024-01-15 ERROR").matches_with_groups(
    r"(\d{4}-\d{2}-\d{2}) (\w+)"
).is_equal_to(("2024-01-15", "ERROR"))

assert_that("key=value").matches_with_groups(
    r"(?P<key>\w+)=(?P<val>\w+)"
).contains_entry({"key": "key"}).contains_entry({"val": "value"})
```
