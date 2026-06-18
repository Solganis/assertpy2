from assertpy2 import assert_that, fail


class CustomList:
    def __init__(self, s):
        self._s = s
        self._idx = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            result = self._s[self._idx]
        except IndexError:
            raise StopIteration from None
        self._idx += 1
        return result

    def __getitem__(self, idx):
        return self._s[idx]


def test_custom_list():
    CustomList("foobar")
    assert_that([CustomList("foo"), CustomList("bar")]).extracting(0, -1).is_equal_to([("f", "o"), ("b", "r")])


def test_check_iterable():
    custom_list = CustomList("foobar")
    ab = assert_that(None)
    ab._check_iterable(custom_list)
    ab._check_iterable(custom_list, check_getitem=True)
    ab._check_iterable(custom_list, check_getitem=False)


def test_check_iterable_not_iterable():
    try:
        ab = assert_that(None)
        ab._check_iterable(123, name="my-int")
        fail("should have raised error")
    except TypeError as e:
        assert_that(str(e)).contains("my-int <int> is not iterable")


def test_check_iterable_no_getitem():
    try:
        ab = assert_that(None)
        ab._check_iterable({1}, name="my-set")
        fail("should have raised error")
    except TypeError as e:
        assert_that(str(e)).contains("my-set <set> does not have [] accessor")
