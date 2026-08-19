"""Hold the order of the `assert_that()` overloads, which nothing else announces when it breaks.

A `pandas.DataFrame` is assignable to *every* structural protocol, because pandas models column access
with a catch-all attribute.  So the frame overload works only while it is the first shape-keyed one: put
anything else above it and every frame silently resolves to that instead, with no error anywhere.  The
same catch-all is why a checker cannot be asked about it cheaply, and why this reads the source instead.

Two gates, deliberately apart.  This one is about what is written, needs no third-party library, and
runs everywhere.  `tests/test_typing.py` is about what a checker picks, and pins each shape to its view
with `assert_type`.  Neither replaces the other: source order can be right while a checker resolves
elsewhere, and a checker can agree today while an edit reorders the file tomorrow.

The public API snapshot records the overloads too, but it is re-recorded whenever the surface moves, so
a broken invariant travels through it as an ordinary diff.  This says the invariant out loud.
"""

from __future__ import annotations

import ast
import pathlib

from assertpy2 import assert_that

_SOURCE = pathlib.Path(__file__).resolve().parent.parent / "assertpy2" / "assertpy.py"


_TYPING = pathlib.Path(__file__).resolve().parent.parent / "assertpy2" / "_engine" / "_typing.py"


def _overload_subjects() -> list[str]:
    """The annotation on ``val`` for each `assert_that` overload, in the order the file declares them."""
    module = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    subjects = []
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef) or node.name != "assert_that":
            continue
        if not any(isinstance(item, ast.Name) and item.id == "overload" for item in node.decorator_list):
            continue
        subjects.append(ast.unparse(node.args.args[0].annotation))
    return subjects


def _shape_bound_typevars() -> dict[str, str]:
    """``{type variable: the shape it is bound to}``, read from where the shapes are declared.

    The overloads key on a bound type variable rather than on the shape itself, so that the view can
    carry the subject type.  Reading the bounds is how this file still knows which overloads are the
    shape-keyed ones, rather than matching on a naming convention that an edit can quietly leave.
    """
    module = ast.parse(_TYPING.read_text(encoding="utf-8"))
    bounds = {}
    for node in ast.walk(module):
        match node:
            case ast.Assign(
                targets=[ast.Name(id=name)],
                value=ast.Call(func=ast.Name(id="TypeVar"), keywords=keywords),
            ):
                for keyword in keywords:
                    # a bound is either one shape by name, or a union of them written as a string
                    # because it is too long for one line.  Reading only the first form is how the
                    # umbrella overload was invisible to this file on the day it was added
                    if keyword.arg == "bound" and isinstance(keyword.value, ast.Name):
                        if keyword.value.id.endswith("Shape"):
                            bounds[name] = keyword.value.id
    return bounds


def _shape_positions(subjects: list[str]) -> list[int]:
    """Where the shape-keyed overloads sit, by the bound of the variable each one keys on."""
    shapes = _shape_bound_typevars()
    return [index for index, name in enumerate(subjects) if name in shapes]


class TestTheOverloadOrder:
    """The frame overload first among the shapes, every shape before the fallback."""

    def test_the_file_declares_overloads_at_all(self):
        # a rename or a refactor that stopped this from finding anything would make every other
        # assertion here vacuous, so the count is asserted before the order is
        assert_that(_overload_subjects()).described_as("overloads of assert_that").is_length(16)

    def test_exactly_one_overload_keys_on_the_frame_shape(self):
        subjects = _overload_subjects()
        frames = [name for name in subjects if _shape_bound_typevars().get(name) == "_FrameShape"]
        assert_that(frames).is_length(1)

    def test_exactly_one_overload_is_the_generic_fallback(self):
        subjects = _overload_subjects()
        assert_that([name for name in subjects if name == "_T"]).is_length(1)

    def test_the_frame_shape_comes_before_every_other_shape(self):
        subjects = _overload_subjects()
        bounds = _shape_bound_typevars()
        frame = next(index for index, name in enumerate(subjects) if bounds.get(name) == "_FrameShape")
        assert_that(frame).described_as(
            "a pandas frame satisfies every shape, so it has to be claimed first"
        ).is_equal_to(min(_shape_positions(subjects)))

    def test_every_shape_comes_before_the_fallback(self):
        subjects = _overload_subjects()
        shapes = _shape_positions(subjects)
        assert_that(max(shapes)).described_as("a shape below the fallback is never reached").is_less_than(
            subjects.index("_T")
        )

    def test_nothing_but_a_shape_sits_between_the_first_shape_and_the_fallback(self):
        subjects = _overload_subjects()
        shapes = _shape_positions(subjects)
        between = subjects[min(shapes) : subjects.index("_T")]
        assert_that([name for name in between if name not in _shape_bound_typevars()]).described_as(
            "an overload wedged into the shape block, which changes what the shapes below it see"
        ).is_empty()
