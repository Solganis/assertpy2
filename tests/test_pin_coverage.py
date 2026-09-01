"""Every view a caller can hold has a pin for each member that changes the type.

Two gates ask about types and they ask different things. `test_typing_completeness.py` asks whether a
checker can *name* a type for each exported symbol, and `test_typing.py` pins that the name is the right
one. A symbol with a named but wrong type passes the first and, until something calls it, is not reached
by the second.

Not every method. Most return `Self`, and a pin on those answers nothing while costing maintenance
forever. The ones worth holding hand back something else, because a pivot returning the wrong view is
silent: the call runs and everything after it is read as a value it is not.

Three things make the set the observable one rather than every declaration:

* the views are resolved from the `assert_that` ladder and closed over what those views return, so a
  protocol nothing hands back is not asked for a pin nothing could write
* a member is taken from the protocol that declares it after MRO resolution, so a base declaration
  every child overrides is not required, and one inherited by seven views is asked for one pin
* a return that is a `TypeVar` is the subject's own type, which a pin necessarily spells concretely, so
  those are matched on the member alone
* a return naming the owner under its own parameters is `Self` by another spelling, which is how the
  capability facade writes it: it stands in for the builder and cannot use `Self`. `_CapableAssertion[_U]`
  from a `_CapableAssertion[_U | None]` receiver is not that, and is asked for a pin

Matched on the member *and* the view it claims, read out of the `assert_type` calls themselves. A member
name alone lets a new pivot ride on the pin for an existing one, and a text search for it matches a
comment.

Every overload return counts, rung by rung. `satisfies`, `is_not_none` and `is_instance_of` each carry
one per view they narrow to, and a rung is an independent mapping from the narrowed type onto the view:
changing one is invisible to a pin on any other.

Rungs returning one view are told apart by what they narrow on, since `satisfies(TypeIs[int])` and
`satisfies(TypeIs[float])` both hand back `_NumericAssertion` and one pin must not answer for both. Each
of the three ladders keeps that in a different place: `satisfies` in a `TypeIs[...]` argument,
`is_instance_of` in a `type[...]` one, `is_not_none` in the `self` annotation.

Four rungs have no portable pin, recorded in `UNPINNABLE` with what refuses them. `is_not_none` on a
nullable `bool`, `int`, `float` or `datetime` resolves to `Unknown` on ty while mypy `--strict` reads all
four correctly, and the badge promises zero suppressions, so there is nowhere to put the difference but
here.
"""

from __future__ import annotations

import ast
import pathlib
import re

from assertpy2 import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SURFACE = _ROOT / "assertpy2" / "_engine" / "_typing.py"
_FACADE = _ROOT / "assertpy2" / "_engine" / "_capable_typing.py"
_LADDER = _ROOT / "assertpy2" / "assertpy.py"
_PINS = _ROOT / "tests" / "test_typing.py"
_UNCHANGED = frozenset({"Self", "None"})
_UNPINNABLE = {
    ("_ObjectAssertion", "is_not_none", "_BoolAssertion", "bool"),
    ("_ObjectAssertion", "is_not_none", "_NumericAssertion[int]", "int"),
    ("_ObjectAssertion", "is_not_none", "_NumericAssertion[float]", "float"),
    ("_ObjectAssertion", "is_not_none", "_DateTimeAssertion", "datetime.datetime"),
    # no expression produces its receiver: a nullable capable value resolves to the object fallback,
    # measured, so `_CapableAssertion[_U | None]` is a `self` nothing hands back
    ("_CapableAssertion", "is_not_none", "_CapableAssertion", "*|None"),
}
"""Rungs no pin can claim, each with what refuses it written above."""
_THE_SUBJECT = "<the subject's own type>"
_NAME = re.compile(r"_[A-Za-z][A-Za-z0-9_]*")


def _parsed(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _view(annotation: str, typevars: frozenset[str] = frozenset()) -> str:
    """The claim a return makes, with its parameters kept when they say something.

    `_NumericAssertion[int]` and `_NumericAssertion[float]` are two claims and must not collapse into
    one. `_ListAssertion[_E]` and `_ListAssertion[Any]` are one, so a parameter that is a `TypeVar` or
    `Any` is dropped. The last dotted segment, since a pin spells `pathlib.Path` where the declaration
    imported `Path`.
    """
    base, _, parameters = annotation.strip().partition("[")
    base = base.rsplit(".", 1)[-1]
    inside = parameters.rstrip("]").strip()
    if not inside or inside == "Any" or any(name in typevars for name in _NAME.findall(inside)):
        return base
    return f"{base}[{', '.join(part.strip().rsplit('.', 1)[-1] for part in inside.split(','))}]"


def _inside(annotation: str, opener: str) -> str:
    """What sits between the brackets of `opener[...]`, brackets inside it included."""
    inside = annotation.partition(opener)[2]
    if not inside:
        return ""
    depth, end = 0, 0
    for end, character in enumerate(inside):  # noqa: B007 - the index is the result
        depth += (character == "[") - (character == "]")
        if depth < 0:
            break
    return inside[:end]


def _flattened(written: str) -> str:
    """Module prefixes dropped and whitespace removed, the way both sides are compared."""
    return "".join(re.sub(r"[A-Za-z_][A-Za-z0-9_]*[.]", "", written).split())


def _narrowed_to(annotation: str, typevars: frozenset[str]) -> str:
    """What a rung narrows to, with type variables wildcarded so the declaration and a pin meet.

    Three shapes because the three ladders keep it in three places, and a rung whose narrowing this
    cannot read carries an empty one, which any pin answers.
    """
    inside = next((found for opener in ("TypeIs[", "type[") if (found := _inside(annotation, opener))), "")
    if not inside and annotation.startswith("_ObjectAssertion["):
        inside = _inside(annotation, "_ObjectAssertion[").removesuffix(" | None")
    if not inside:
        return ""
    written = inside
    for name in sorted(set(_NAME.findall(written)), key=len, reverse=True):
        if name in typevars:
            written = written.replace(name, "*")
    return _flattened(written)


def _predicates() -> dict[str, str]:
    """The `_is_*` helpers in the pin file, mapped to what each narrows to."""
    return {
        node.name: _narrowed_to(ast.unparse(node.returns), frozenset())
        for node in ast.walk(_parsed(_PINS))
        if isinstance(node, ast.FunctionDef) and node.returns is not None and "TypeIs[" in ast.unparse(node.returns)
    }


def _protocols() -> dict[str, ast.ClassDef]:
    """The views, and the two a pivot hands back that are declared elsewhere.

    `AssertionBuilder` is what a capability-keyed `satisfies` returns and `_CapableAssertion` is what
    `assert_that` returns for a value it recognises without naming, so both are reachable and neither
    lives in `_typing.py`. Their bases are the runtime mixins, which declare no views and are left out.
    """
    found = {node.name: node for node in ast.walk(_parsed(_SURFACE)) if isinstance(node, ast.ClassDef)}
    for path, wanted in ((_LADDER, "AssertionBuilder"), (_FACADE, "_CapableAssertion")):
        found.update(
            {
                node.name: node
                for node in ast.walk(_parsed(path))
                if isinstance(node, ast.ClassDef) and node.name == wanted
            }
        )
    return found


def _typevars() -> set[str]:
    """From all three files, since the facade declares its own and its returns are read here."""
    return {
        node.targets[0].id
        for path in (_SURFACE, _FACADE, _LADDER)
        for node in ast.walk(_parsed(path))
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", None) == "TypeVar"
    }


def _itself(owner: str, protocols: dict[str, ast.ClassDef]) -> set[str]:
    """How a protocol spells "the same view again", which is `Self` for everything that can say it.

    The facade and the builder cannot: one stands in for the other. Only the owner under its own
    parameters counts, so a rung narrowing `_CapableAssertion[_U | None]` to `_CapableAssertion[_U]`
    stays a pivot.
    """
    node = protocols.get(owner)
    if node is None:
        return {owner}
    own = [
        parameter
        for base in node.bases
        for parameter in _inside(ast.unparse(base), "Protocol[").split(",")
        + _inside(ast.unparse(base), "Generic[").split(",")
        if parameter.strip()
    ]
    return {owner, _flattened(f"{owner}[{','.join(parameter.strip() for parameter in own)}]")}


def _members(
    name: str, protocols: dict[str, ast.ClassDef], seen: frozenset[str] = frozenset()
) -> dict[str, tuple[str, list[str]]]:
    """Member to its owner and every overload's return, bases first so a child shadows what it overrides."""
    if name in seen or name not in protocols:
        return {}
    node = protocols[name]
    found: dict[str, tuple[str, list[str]]] = {}
    for base in _NAME.findall(", ".join(ast.unparse(base) for base in node.bases)):
        found.update(_members(base, protocols, seen | {name}))
    declared: dict[str, list[tuple[str, str]]] = {}
    for body in node.body:
        if (
            isinstance(body, ast.FunctionDef)
            and body.returns is not None
            and (not body.name.startswith("_") or body.name == "not_")
        ):
            arguments = [
                ast.unparse(argument.annotation) for argument in body.args.args if argument.annotation is not None
            ]
            narrows = " ".join(arguments)
            declared.setdefault(body.name, []).append((ast.unparse(body.returns), narrows))
    found.update({member: (name, returns) for member, returns in declared.items()})
    return found


def _views_a_caller_can_hold(protocols: dict[str, ast.ClassDef]) -> set[str]:
    """The ladder's own returns, then everything those views hand back, to a fixed point."""
    held = {
        name
        for node in ast.walk(_parsed(_LADDER))
        if isinstance(node, ast.FunctionDef) and node.name == "assert_that" and node.returns is not None
        for name in _NAME.findall(ast.unparse(node.returns))
        if name in protocols
    }
    frontier = set(held)
    while frontier:
        reached = {
            name
            for view in frontier
            for _, returns in _members(view, protocols).values()
            for returned, _narrows in returns
            for name in _NAME.findall(returned)
            if name in protocols and name not in held
        }
        held |= reached
        frontier = reached
    return held


def _required() -> dict[tuple[str, str], set[tuple[str, str]]]:
    """Owner and member to what each rung hands back and what it narrows on, if anything."""
    protocols = _protocols()
    typevars = _typevars()
    claims: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for view in _views_a_caller_can_hold(protocols):
        for member, (owner, returns) in _members(view, protocols).items():
            changing = {
                (
                    _THE_SUBJECT if returned.strip() in typevars else _view(returned, frozenset(typevars)),
                    _narrowed_to(narrows, frozenset(typevars)),
                )
                for returned, narrows in returns
                if returned not in _UNCHANGED and _flattened(returned) not in _itself(owner, protocols)
            }
            if changing:
                claims.setdefault((owner, member), set()).update(changing)
    # a narrowing only earns its place where two rungs would otherwise be one requirement
    return {
        key: {
            (claim, narrowed if sum(1 for other, _ in rungs if other == claim) > 1 else "") for claim, narrowed in rungs
        }
        for key, rungs in claims.items()
    }


_SUBJECTS = {
    "Dict": "_DictAssertion",
    "List": "_IterableAssertion",
    "Set": "_IterableAssertion",
    "Tuple": "_IterableAssertion",
    "Lambda": "_CallableAssertion",
    "str": "_StringAssertion",
    "bool": "_BoolAssertion",
    "int": "_NumericAssertion",
    "float": "_NumericAssertion",
    "complex": "_ComplexAssertion",
    "bytes": "_BytesAssertion",
    # written as a call rather than a literal, keyed by what is called
    "object": "_ObjectAssertion",
    "bytearray": "_BytesAssertion",
    "frozenset": "_IterableAssertion",
    "set": "_IterableAssertion",
    "Path": "_PathAssertion",
    "date": "_DateAssertion",
    "datetime": "_DateTimeAssertion",
    # the stand-ins the pin file defines for a value the umbrella claims
    "_Countable": "_CapableAssertion",
    "_CallableResponse": "_CapableAssertion",
    "_FakeResponse": "_CapableAssertion",
    "_Rowish": "_CapableAssertion",
}
"""What `assert_that(<this>)` hands back, for the literal forms the pins are written with.

Only enough to tell the three `satisfies` ladders apart, which is where one pin covered three owners.
A receiver this cannot read counts for every owner, which is the permissive direction: it can leave a
rung unrequired, never require one that does not exist.
"""


def _chain(expression: ast.expr) -> list[str] | None:
    """The members reached, outermost last, or `None` if the chain does not start at `assert_that`."""
    steps: list[str] = []
    node = expression
    while True:
        if isinstance(node, ast.Call):
            if getattr(node.func, "id", None) == "assert_that":
                return steps[::-1]
            node = node.func
        elif isinstance(node, ast.Attribute):
            steps.append(node.attr)
            node = node.value
        else:
            return None


def _starting_view(expression: ast.expr) -> str | None:
    """What `assert_that(<this>)` hands back, read off the subject it was given.

    A literal by its kind, a call by what it calls, a `cast` by the shape it names: `_FrameShape` is what
    the frame view is keyed on, and the two are one rename apart.
    """
    for node in ast.walk(expression):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "assert_that" and node.args):
            continue
        given = node.args[0]
        if isinstance(given, ast.Constant):
            return _SUBJECTS.get(type(given.value).__name__)
        if isinstance(given, ast.Call):
            called = getattr(given.func, "id", None) or getattr(given.func, "attr", None) or ""
            if called == "cast" and given.args:
                named = ast.literal_eval(given.args[0]) if isinstance(given.args[0], ast.Constant) else ""
                return named.replace("Shape", "Assertion") if named.endswith("Shape") else None
            return _SUBJECTS.get(called)
        return _SUBJECTS.get(type(given).__name__)
    return None


def _receiver_view(expression: ast.expr, protocols: dict[str, ast.ClassDef]) -> str | None:
    """The view the outermost member is reached on, followed step by step down the chain.

    `assert_that([...]).extracting(...).check()` reaches `check` on the list view, not on the iterable
    one it started from, and pinning the twin of the wrong view is exactly what this file is about.
    """
    view = _starting_view(expression)
    steps = _chain(expression)
    if view is None or steps is None:
        return None
    for step in steps[:-1]:
        _, returns = _members(view, protocols).get(step, (None, []))
        moved = {_view(returned).split("[", 1)[0] for returned, _narrows in returns}
        moved = {name for name in moved if name in protocols}
        if len(moved) != 1:
            return None
        view = moved.pop()
    return view


def _pin_narrowing(expression: ast.expr, member: str, predicates: dict[str, str]) -> str:
    """What this pin narrows on, taken from wherever the member keeps it.

    `satisfies` from the helper it is given, `is_instance_of` from the class, `is_not_none` from the
    `cast` the subject was written as. Anything else has none, which every rung answers.
    """
    if member == "satisfies":
        given = expression.args[0] if isinstance(expression, ast.Call) and expression.args else None
        return predicates.get(getattr(given, "id", ""), "")
    if member == "is_instance_of":
        given = expression.args[0] if isinstance(expression, ast.Call) and expression.args else None
        if isinstance(given, ast.Call) and getattr(given.func, "id", None) == "cast":
            return _flattened(_inside(ast.literal_eval(given.args[0]), "type["))
        return _flattened(ast.unparse(given)) if given is not None else ""
    if member == "is_not_none":
        for node in ast.walk(expression):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "cast" and node.args:
                return _flattened(ast.literal_eval(node.args[0]).removesuffix(" | None"))
    return ""


def _pinned(protocols: dict[str, ast.ClassDef]) -> set[tuple[str | None, str, str, str]]:
    """What each `assert_type` call pins: the owner it reaches the member on, and the view it claims.

    Only the outermost member of the chain. `assert_type(x.first().value, int)` pins `value`, and says
    nothing about `first` beyond that it exists.
    """
    pins: set[tuple[str | None, str, str, str]] = set()
    predicates = _predicates()
    for node in ast.walk(_parsed(_PINS)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "assert_type" and len(node.args) == 2):
            continue
        outermost = node.args[0]
        while isinstance(outermost, ast.Call):
            outermost = outermost.func
        if not isinstance(outermost, ast.Attribute):
            continue
        view = _receiver_view(node.args[0], protocols)
        owner = None if view is None else _members(view, protocols).get(outermost.attr, (None, []))[0]
        claimed = _view(ast.unparse(node.args[1]))
        narrowed = _pin_narrowing(node.args[0], outermost.attr, predicates)
        pins |= {
            (owner, outermost.attr, claim, narrowed) for claim in (claimed, claimed.split("[", 1)[0], _THE_SUBJECT)
        }
    return pins


def _answers(pattern: str, narrowed: str) -> bool:
    """A rung's `*` stands for a type variable, and a pin fills it in with something concrete.

    A rung narrowing on a union is answered by a pin narrowing on any one of its arms: `list[str]` is
    what a caller writes for a rung declared `list[_E] | tuple[_E, ...]`. A rung with nothing to be told
    apart from carries no pattern, and any pin answers it.
    """
    return not pattern or any(re.fullmatch(re.escape(arm).replace(r"\*", ".+"), narrowed) for arm in pattern.split("|"))


def _only_owner_of(
    member: str, claim: str, narrowed: str, required: dict[tuple[str, str], set[tuple[str, str]]]
) -> str | None:
    """The one owner declaring this member, claim and narrowing, or `None` when several do.

    A pin whose receiver could not be read counts only where there is nothing to confuse it with.
    """
    owners = {owner for (owner, name), claims in required.items() if name == member and (claim, narrowed) in claims}
    return owners.pop() if len(owners) == 1 else None


def test_every_type_changing_member_is_pinned() -> None:
    """Named rather than counted, so the failure says which pin to write."""
    pinned = _pinned(_protocols())
    required = _required()
    unpinned = sorted(
        f"{owner}.{member} -> {claim}" + (f" narrowing on {narrowed}" if narrowed else "")
        for (owner, member), claims in required.items()
        for claim, narrowed in claims
        if not any(
            (
                pinned_owner == owner
                or (pinned_owner is None and _only_owner_of(member, claim, narrowed, required) == owner)
            )
            and pinned_member == member
            and pinned_claim == claim
            and _answers(narrowed, pinned_narrowing)
            for pinned_owner, pinned_member, pinned_claim, pinned_narrowing in pinned
        )
        and not any(
            (recorded_owner, recorded_member, recorded_claim) == (owner, member, claim)
            and _answers(narrowed, recorded_narrowing)
            for recorded_owner, recorded_member, recorded_claim, recorded_narrowing in _UNPINNABLE
        )
    )

    assert_that(unpinned).described_as(
        "members handing back something other than `Self` with no `assert_type` pinning what"
    ).is_empty()


def test_no_recorded_rung_became_pinnable() -> None:
    """Fails when somebody writes a pin for a rung recorded as unpinnable, and only then.

    It cannot notice ty growing the ability on its own: that shows up when someone tries the pin again.
    The record names what to try, and the four expressions are one line each.
    """
    pinned = _pinned(_protocols())
    stale = sorted(
        f"{owner}.{member} -> {claim}"
        for owner, member, claim, narrowed in _UNPINNABLE
        if any(
            pin_owner in (owner, None)
            and pin_member == member
            and pin_claim == claim
            and _answers(narrowed, pin_narrowing)
            for pin_owner, pin_member, pin_claim, pin_narrowing in pinned
        )
    )

    assert_that(stale).described_as("rungs recorded as unpinnable that something now pins").is_empty()


def test_there_is_something_on_both_sides() -> None:
    """Empty sets would make the claim above vacuous rather than false."""
    assert_that(_views_a_caller_can_hold(_protocols())).is_not_empty()
    assert_that(_required()).is_not_empty()
    assert_that(_pinned(_protocols())).is_not_empty()
