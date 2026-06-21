from __future__ import annotations

import collections.abc

from ._introspection import is_namedtuple
from ._mixin_base import _MixinBase

__tracebackhide__ = True


class DynamicMixin(_MixinBase):
    """Dynamic assertions mixin.

    When testing attributes of an object (or the contents of a dict), the
    :meth:`~assertpy.base.BaseMixin.is_equal_to` assertion can be a bit verbose::

        fred = Person('Fred', 'Smith')

        assert_that(fred.first_name).is_equal_to('Fred')
        assert_that(fred.name).is_equal_to('Fred Smith')
        assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')

    Instead, use dynamic assertions in the form of ``has_<name>()`` where ``<name>`` is the name of
    any attribute, property, or zero-argument method on the given object. Dynamic equality
    assertions test if actual is equal to expected using the ``==`` operator. Using dynamic
    assertions, we can rewrite the above example as::

        assert_that(fred).has_first_name('Fred')
        assert_that(fred).has_name('Fred Smith')
        assert_that(fred).has_say_hello('Hello, Fred!')

    Similarly, dynamic assertions also work on any *dict-like* object::

        fred = {
            'first_name': 'Fred',
            'last_name': 'Smith',
            'shoe_size': 12
        }

        assert_that(fred).has_first_name('Fred')
        assert_that(fred).has_last_name('Smith')
        assert_that(fred).has_shoe_size(12)
    """

    def __getattr__(self, attr):
        """Asserts that val has attribute attr and that its value is equal to other via a dynamic
        assertion of the form ``has_<attr>()``."""
        if not attr.startswith("has_"):
            raise AttributeError(f"assertpy has no assertion <{attr}()>")

        attr_name = attr[4:]
        err_msg = False
        val_is_namedtuple = is_namedtuple(self.val)
        is_dict = isinstance(self.val, collections.abc.Iterable) and hasattr(self.val, "__getitem__")

        if not hasattr(self.val, attr_name):
            if is_dict and not val_is_namedtuple:
                if attr_name not in self.val:
                    err_msg = f"Expected key <{attr_name}>, but val has no key <{attr_name}>."
            else:
                err_msg = f"Expected attribute <{attr_name}>, but val has no attribute <{attr_name}>."

        def _wrapper(*args, **kwargs):
            if err_msg:
                return self.error(err_msg)  # ok to raise AssertionError now that we are inside wrapper
            else:
                if len(args) != 1:
                    raise TypeError(f"assertion <{attr}()> takes exactly 1 argument ({len(args)} given)")

                val_attr = self.val[attr_name] if is_dict and not val_is_namedtuple else getattr(self.val, attr_name)

                if callable(val_attr):
                    try:
                        actual = val_attr()
                    except TypeError:
                        raise TypeError(f"val does not have zero-arg method <{attr_name}()>") from None
                else:
                    actual = val_attr

                expected = args[0]
                if actual != expected:
                    kind = "key" if is_dict else "attribute"
                    return self.error(
                        f"Expected <{actual}> to be equal to <{expected}> on {kind} <{attr_name}>, but was not."
                    )
            return self

        return _wrapper
