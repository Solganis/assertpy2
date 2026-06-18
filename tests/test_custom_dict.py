import pytest

from assertpy2 import assert_that, fail


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
    builder._check_dict_like(custom_dict)
    builder._check_dict_like(custom_dict, True, True, True)
    builder._check_dict_like(custom_dict, True, True, False)
    builder._check_dict_like(custom_dict, True, False, True)
    builder._check_dict_like(custom_dict, False, True, True)
    builder._check_dict_like(custom_dict, True, False, False)
    builder._check_dict_like(custom_dict, False, False, True)
    builder._check_dict_like(custom_dict, False, True, False)
    builder._check_dict_like(custom_dict, False, False, False)

    builder._check_dict_like(CustomDictNoKeys(), check_keys=False, check_values=False, check_getitem=False)
    builder._check_dict_like(CustomDictNoKeysCallable(), check_keys=False, check_values=False, check_getitem=False)
    builder._check_dict_like(CustomDictNoValues(), check_values=False, check_getitem=False)
    builder._check_dict_like(CustomDictNoValuesCallable(), check_values=False, check_getitem=False)
    builder._check_dict_like(CustomDictNoGetitem(), check_getitem=False)


def test_check_dict_like_bool():
    builder = assert_that(None)
    assert_that(builder._check_dict_like(CustomDictNoKeys(), return_as_bool=True)).is_false()
    assert_that(builder._check_dict_like(CustomDictNoKeysCallable(), return_as_bool=True)).is_false()
    assert_that(builder._check_dict_like(CustomDictNoValues(), return_as_bool=True)).is_false()
    assert_that(builder._check_dict_like(CustomDictNoValuesCallable(), return_as_bool=True)).is_false()
    assert_that(builder._check_dict_like(CustomDictNoGetitem(), return_as_bool=True)).is_false()


def test_check_dict_like_no_keys():
    try:
        builder = assert_that(None)
        builder._check_dict_like(CustomDictNoKeys())
        fail("should have raised error")
    except TypeError as e:
        assert_that(str(e)).contains("is not dict-like: missing keys()")


def test_check_dict_like_no_keys_callable():
    try:
        builder = assert_that(None)
        builder._check_dict_like(CustomDictNoKeysCallable())
        fail("should have raised error")
    except TypeError as e:
        assert_that(str(e)).contains("is not dict-like: missing keys()")


def test_check_dict_like_no_values():
    try:
        builder = assert_that(None)
        builder._check_dict_like(CustomDictNoValues())
        fail("should have raised error")
    except TypeError as e:
        assert_that(str(e)).contains("is not dict-like: missing values()")


def test_check_dict_like_no_values_callable():
    try:
        builder = assert_that(None)
        builder._check_dict_like(CustomDictNoValuesCallable())
        fail("should have raised error")
    except TypeError as e:
        assert_that(str(e)).contains("is not dict-like: missing values()")


def test_check_dict_like_no_getitem():
    try:
        builder = assert_that(None)
        builder._check_dict_like(CustomDictNoGetitem())
        fail("should have raised error")
    except TypeError as e:
        assert_that(str(e)).contains("is not dict-like: missing [] accessor")


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
