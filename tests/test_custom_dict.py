import pytest

from assertpy2 import assert_that


def test_custom_dict():
    headers = CustomDict(
        {
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Accept": "application/json",
            "User-Agent": "python-requests/2.9.1",
        }
    )

    assert_that(headers).is_not_none()

    assert_that(headers.keys()).contains("Accept-Encoding", "Connection", "Accept", "User-Agent")
    assert_that(headers).contains_key("Accept-Encoding", "Connection", "Accept", "User-Agent")

    assert_that(headers.values()).contains("gzip, deflate", "keep-alive", "application/json", "python-requests/2.9.1")
    assert_that(headers).contains_value("application/json")

    assert_that(headers["Accept"]).is_equal_to("application/json")
    assert_that(headers).contains_entry({"Accept": "application/json"})


def test_requests():
    requests = pytest.importorskip("requests")
    headers = requests.structures.CaseInsensitiveDict(
        {
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Accept": "application/json",
            "User-Agent": "python-requests/2.9.1",
        }
    )

    assert_that(headers).is_not_none()

    assert_that(headers.keys()).contains("Accept-Encoding", "Connection", "Accept", "User-Agent")
    assert_that(headers).contains_key("Accept-Encoding", "Connection", "Accept", "User-Agent")

    assert_that(headers.values()).contains("gzip, deflate", "keep-alive", "application/json", "python-requests/2.9.1")
    assert_that(headers).contains_value("application/json")

    assert_that(headers["Accept"]).is_equal_to("application/json")
    assert_that(headers).contains_entry({"Accept": "application/json"})


class CustomDict:
    def __init__(self, d):
        self._dict = d
        self._idx = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            result = self.keys()[self._idx]
        except IndexError:
            raise StopIteration from None
        self._idx += 1
        return result

    def __contains__(self, key):
        return key in self.keys()

    def keys(self):
        return list(self._dict.keys())

    def values(self):
        return list(self._dict.values())

    def __getitem__(self, key):
        return self._dict.get(key)


def test_check_dict_like():
    custom_dict = CustomDict({"a": 1})
    builder = assert_that(None)
    builder._require_dict_like(custom_dict)
    builder._require_dict_like(custom_dict, True, True, True)
    builder._require_dict_like(custom_dict, True, True, False)
    builder._require_dict_like(custom_dict, True, False, True)
    builder._require_dict_like(custom_dict, False, True, True)
    builder._require_dict_like(custom_dict, True, False, False)
    builder._require_dict_like(custom_dict, False, False, True)
    builder._require_dict_like(custom_dict, False, True, False)
    builder._require_dict_like(custom_dict, False, False, False)

    builder._require_dict_like(CustomDictNoKeys(), check_keys=False, check_values=False, check_getitem=False)
    builder._require_dict_like(CustomDictNoKeysCallable(), check_keys=False, check_values=False, check_getitem=False)
    builder._require_dict_like(CustomDictNoValues(), check_values=False, check_getitem=False)
    builder._require_dict_like(CustomDictNoValuesCallable(), check_values=False, check_getitem=False)
    builder._require_dict_like(CustomDictNoGetitem(), check_getitem=False)


def test_check_dict_like_bool():
    builder = assert_that(None)
    assert_that(builder._is_dict_like(CustomDictNoKeys())).is_false()
    assert_that(builder._is_dict_like(CustomDictNoKeysCallable())).is_false()
    assert_that(builder._is_dict_like(CustomDictNoValues())).is_false()
    assert_that(builder._is_dict_like(CustomDictNoValuesCallable())).is_false()
    assert_that(builder._is_dict_like(CustomDictNoGetitem())).is_false()


def test_check_dict_like_no_keys():
    with pytest.raises(TypeError) as exc_info:
        builder = assert_that(None)
        builder._require_dict_like(CustomDictNoKeys())
    assert_that(str(exc_info.value)).contains("is not dict-like: missing keys()")


def test_check_dict_like_no_keys_callable():
    with pytest.raises(TypeError) as exc_info:
        builder = assert_that(None)
        builder._require_dict_like(CustomDictNoKeysCallable())
    assert_that(str(exc_info.value)).contains("is not dict-like: missing keys()")


def test_check_dict_like_no_values():
    with pytest.raises(TypeError) as exc_info:
        builder = assert_that(None)
        builder._require_dict_like(CustomDictNoValues())
    assert_that(str(exc_info.value)).contains("is not dict-like: missing values()")


def test_check_dict_like_no_values_callable():
    with pytest.raises(TypeError) as exc_info:
        builder = assert_that(None)
        builder._require_dict_like(CustomDictNoValuesCallable())
    assert_that(str(exc_info.value)).contains("is not dict-like: missing values()")


def test_check_dict_like_no_getitem():
    with pytest.raises(TypeError) as exc_info:
        builder = assert_that(None)
        builder._require_dict_like(CustomDictNoGetitem())
    assert_that(str(exc_info.value)).contains("is not dict-like: missing [] accessor")


class CustomDictNoKeys:
    def __iter__(self):
        return self

    def __next__(self):
        return 1


class CustomDictNoKeysCallable:
    def __init__(self):
        self.keys = "foo"

    def __iter__(self):
        return self

    def __next__(self):
        return 1


class CustomDictNoValues:
    def __iter__(self):
        return self

    def __next__(self):
        return 1

    def keys(self):
        return "foo"


class CustomDictNoValuesCallable:
    def __init__(self):
        self.values = "foo"

    def __iter__(self):
        return self

    def __next__(self):
        return 1

    def keys(self):
        return "foo"


class CustomDictNoGetitem:
    def __iter__(self):
        return self

    def __next__(self):
        return 1

    def keys(self):
        return "foo"

    def values(self):
        return "bar"


def test_dict_repr_survives_mapping_without_items():
    # the failure-message renderer must build entries from keys()+[]; a minimal mapping-like value may
    # lack items(), and rendering the diff must not crash with AttributeError
    class MinimalMapping:
        def __init__(self, data):
            self._data = data

        def keys(self):
            return self._data.keys()

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

    with pytest.raises(AssertionError):
        assert_that(MinimalMapping({"a": 1, "b": 2})).is_equal_to(MinimalMapping({"a": 1, "b": 3}))


def test_nested_mapping_without_values_still_takes_the_dict_path():
    # a nested value is matched with check_values=False on purpose: a mapping that lacks values() must
    # still be compared key-by-key, so a nested ignore path reaches into it. Demanding values() here
    # would drop it to a plain equality check and the ignore would silently stop applying.
    class MinimalMapping:
        def __init__(self, data):
            self._data = data

        def keys(self):
            return self._data.keys()

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

    actual = {"d": MinimalMapping({"a": 1, "b": 2})}
    expected = {"d": MinimalMapping({"a": 1, "b": 999})}
    assert_that(actual).is_equal_to(expected, ignore=("d", "b"))
