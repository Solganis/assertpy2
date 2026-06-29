from __future__ import annotations

import collections.abc
from typing import TYPE_CHECKING

from ._introspection import is_model_dump_object, is_namedtuple
from ._mixin_base import _MixinBase

if TYPE_CHECKING:
    from ._compat import Self

__tracebackhide__ = True


class ExtractingMixin(_MixinBase):
    """Collection flattening mixin.

    It is often necessary to test collections of objects.  Use the ``extracting()`` helper to
    reduce the collection on a given attribute.  Reduce a list of objects:

        alice = Person('Alice', 'Alpha')
        bob = Person('Bob', 'Bravo')
        people = [alice, bob]

        assert_that(people).extracting('first_name').is_equal_to(['Alice', 'Bob'])
        assert_that(people).extracting('first_name').contains('Alice', 'Bob')
        assert_that(people).extracting('first_name').does_not_contain('Charlie')

    Additionally, the ``extracting()`` helper can accept a list of attributes to be extracted, and
    will flatten them into a list of tuples.  Reduce a list of objects on multiple attributes:

        assert_that(people).extracting('first_name', 'last_name').contains(('Alice', 'Alpha'), ('Bob', 'Bravo'))

    Also, ``extracting()`` works on not just attributes, but also properties, and even
    zero-argument methods.  Reduce a list of object on properties and zero-arg methods:

        assert_that(people).extracting('name').contains('Alice Alpha', 'Bob Bravo')
        assert_that(people).extracting('say_hello').contains('Hello, Alice!', 'Hello, Bob!')

    And ``extracting()`` even works on *dict-like* objects.  Reduce a list of dicts on key:

        alice = {'first_name': 'Alice', 'last_name': 'Alpha'}
        bob = {'first_name': 'Bob', 'last_name': 'Bravo'}
        people = [alice, bob]

        assert_that(people).extracting('first_name').contains('Alice', 'Bob')

    **Filtering**

    The ``extracting()`` helper can include a *filter* to keep only those items for which the given
    *filter* is truthy.  For example:

        users = [
            {'user': 'Alice', 'age': 36, 'active': True},
            {'user': 'Bob', 'age': 40, 'active': False},
            {'user': 'Charlie', 'age': 13, 'active': True}
        ]

        # filter the active users
        assert_that(users).extracting('user', filter='active').is_equal_to(['Alice', 'Charlie'])

    The *filter* can be a *dict-like* object and the extracted items are kept if and only if all
    corresponding key-value pairs are equal:

        assert_that(users).extracting('user', filter={'active': False}).is_equal_to(['Bob'])
        assert_that(users).extracting('user', filter={'age': 36, 'active': True}).is_equal_to(['Alice'])

    Or a *filter* can be any function (including an in-line ``lambda``) that accepts as its single
    argument each item in the collection, and the extracted items are kept if the function
    evaluates to ``True``:

        assert_that(users).extracting('user', filter=lambda x: x['age'] > 20)
            .is_equal_to(['Alice', 'Bob'])

    **Sorting**

    The ``extracting()`` helper can include a *sort* to enforce order on the extracted items.

    The *sort* can be the name of a key (or attribute, or property, or zero-argument method) and
    the extracted items are ordered by the corresponding values:

        assert_that(users).extracting('user', sort='age').is_equal_to(['Charlie', 'Alice', 'Bob'])

    The *sort* can be an iterable of names and the extracted items are ordered by
    corresponding value of the first name, ties are broken by the corresponding values of the
    second name, and so on:

        assert_that(users).extracting('user', sort=['active', 'age']).is_equal_to(['Bob', 'Charlie', 'Alice'])

    The *sort* can be any function (including an in-line ``lambda``) that accepts as its single
    argument each item in the collection, and the extracted items are ordered by the corresponding
    function return values:

        assert_that(users).extracting('user', sort=lambda x: -x['age']).is_equal_to(['Bob', 'Alice', 'Charlie'])
    """

    def extracting(self, *names: object, **kwargs) -> Self:
        """Asserts that val is iterable, then extracts the named attributes, properties, or
        zero-arg methods into a list (or list of tuples if multiple names are given).

        Args:
            *names: the attribute to be extracted (or property or zero-arg method)
            **kwargs (object): see below

        Keyword Args:
            filter (str | dict | Callable | None): extract only those items where filter is truthy
            sort (str | Iterable | Callable | None): order the extracted items by the sort key

        Examples:
            Usage:

                alice = User('Alice', 20, True)
                bob = User('Bob', 30, False)
                charlie = User('Charlie', 10, True)
                users = [alice, bob, charlie]

                assert_that(users).extracting('user').contains('Alice', 'Bob', 'Charlie')

            Works with *dict-like* objects too:

                users = [
                    {'user': 'Alice', 'age': 20, 'active': True},
                    {'user': 'Bob', 'age': 30, 'active': False},
                    {'user': 'Charlie', 'age': 10, 'active': True}
                ]

                assert_that(people).extracting('user').contains('Alice', 'Bob', 'Charlie')

            Filter:

                assert_that(users).extracting('user', filter='active').is_equal_to(['Alice', 'Charlie'])

            Sort:

                assert_that(users).extracting('user', sort='age').is_equal_to(['Charlie', 'Alice', 'Bob'])

        Returns:
            AssertionBuilder: returns a new instance (extracted list as val) to chain the next assertion
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        if isinstance(self.val, str):
            raise TypeError("val must not be string")
        if len(names) == 0:
            raise ValueError("one or more name args must be given")

        def _extract(item, name):
            if self._is_dict_like(item, check_values=False):
                if name in item:
                    return item[name]
                else:
                    raise ValueError(f"item keys {list(item.keys())} did not contain key <{name}>")
            elif is_namedtuple(item) and type(name) is str:
                if name in item._fields:
                    return getattr(item, name)
                else:  # val has no attribute <foo>
                    raise ValueError(f"item attributes {item._fields} did not contain attribute <{name}>")
            elif isinstance(item, collections.abc.Iterable) and not is_model_dump_object(item):
                self._check_iterable(item, name="item")
                return item[name]
            elif hasattr(item, name):
                attr = getattr(item, name)
                if callable(attr):
                    try:
                        return attr()
                    except TypeError:
                        raise ValueError(f"item method <{name}()> exists, but is not zero-arg method") from None
                else:
                    return attr
            else:
                raise ValueError(f"item does not have property or zero-arg method <{name}>")

        def _filter(item):
            if "filter" in kwargs:
                if isinstance(kwargs["filter"], str):
                    return bool(_extract(item, kwargs["filter"]))
                elif self._is_dict_like(kwargs["filter"], check_values=False):
                    for key in kwargs["filter"]:
                        if isinstance(key, str) and _extract(item, key) != kwargs["filter"][key]:
                            return False
                    return True
                elif callable(kwargs["filter"]):
                    return kwargs["filter"](item)
                elif kwargs["filter"] is None:
                    return True
                raise TypeError(
                    f"given filter arg must be a str, dict, or callable, but was <{type(kwargs['filter']).__name__}>"
                )
            return True

        def _sort(item):
            if "sort" in kwargs:
                if isinstance(kwargs["sort"], str):
                    return _extract(item, kwargs["sort"])
                elif isinstance(kwargs["sort"], collections.abc.Iterable):
                    sort_keys = [_extract(item, key) for key in kwargs["sort"] if isinstance(key, str)]
                    return tuple(sort_keys)
                elif callable(kwargs["sort"]):
                    return kwargs["sort"](item)
            return 0

        extracted = []
        for item in sorted(self.val, key=lambda value: _sort(value)):
            if _filter(item):
                extracted_values = [_extract(item, name) for name in names]
                extracted.append(tuple(extracted_values) if len(extracted_values) > 1 else extracted_values[0])

        # chain on with _extracted_ list (don't chain to self!)
        return self.builder(extracted, self.description, self.kind)
