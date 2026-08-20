"""Run the consumer corpus: build the package, install it, and check somebody else's code against it.

`tests/` imports the source tree.  This installs a build instead, one environment per project, to ask
the two questions that cannot be asked from inside the repository: does the wheel carry what it
promises, and does the typed surface fit code written by someone who has not read it.

    python corpus/run.py [--from wheel|sdist] [--only NAME ...] [--checkers NAME ...]
                         [--python 3.10] [--keep] [--json FILE]

A project is a directory under `corpus/projects/` with a `corpus.toml`; nothing else is wired by hand.
What earns a new one is a *shape of consumer code not already exercised*, named in its `shape` field,
rather than more assertions.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys

import tomllib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CORPUS = _ROOT / "corpus"
_PROJECTS = _CORPUS / "projects"
# one directory per run: two at once were deleting each other's environments, and a pid alone is not
# enough, since the OS reuses them
_RUN = f"{os.getpid()}-{secrets.token_hex(4)}"
_CONSUMER_PYTHON: str | None = None
_ENVIRONMENTS = _CORPUS / ".envs" / _RUN
_BUILDS = _CORPUS / ".builds" / _RUN

# every checker the library promises to satisfy, and the argv that asks it about a directory.  How
# strictly is the project's own business: a first-time user does not run `mypy --strict`, and a typed
# codebase does, and a surface that only fits one of them fits neither in practice
_CHECKERS = {
    "mypy": ("mypy", "--cache-dir", "{cache}/mypy", "."),
    "pyright": ("pyright", "--pythonpath", "{python}", "."),
    "ty": ("ty", "check", "--python", "{python}", "."),
}
# only mypy takes its strictness from the command line; pyright reads `typeCheckingMode` from the
# project's own configuration, which is where a strict consumer would put it anyway
_STRICT = {"mypy": ("mypy", "--strict", "--cache-dir", "{cache}/mypy", ".")}

# constrained to a major line, not pinned: a release inside the line changing a diagnostic is part of
# what this corpus is for, and the artefact records which version produced the verdict
_TOOLS_BY_NAME = {
    "mypy": "mypy>=2.3,<3",
    "pyright": "pyright>=1.1.411,<2",
    "ty": "ty>=0.0.71,<0.1",
}
_TOOLS = ("pytest>=9.1,<10", "packaging>=24,<26")
# the one tool the inventory itself needs, kept separate because the baseline install gets only this
_INSTRUMENT = "packaging>=24,<26"
_RECORDED = frozenset({"pytest", "packaging"})


@dataclasses.dataclass(frozen=True)
class Project:
    """One consumer, read from its `corpus.toml`."""

    name: str
    path: pathlib.Path
    shape: str
    extras: tuple[str, ...]
    requires: tuple[str, ...]
    checkers: tuple[str, ...]
    mypy_strict: bool

    @classmethod
    def read(cls, path: pathlib.Path) -> Project:
        settings = tomllib.loads((path / "corpus.toml").read_text(encoding="utf-8"))
        consumer = settings["consumer"]
        checkers = tuple(consumer.get("checkers", tuple(_CHECKERS)))
        unknown = sorted(set(checkers) - set(_CHECKERS))
        if unknown:
            raise SystemExit(f"{path.name} asks for checkers nobody runs here: {', '.join(unknown)}")
        return cls(
            name=path.name,
            path=path,
            # what shape of consumer code this brings, so a new project has to justify itself
            shape=consumer["shape"],
            extras=tuple(_canonical(extra) for extra in consumer.get("extras", ())),
            requires=tuple(consumer.get("requires", ())),
            checkers=checkers,
            mypy_strict=bool(consumer.get("mypy_strict", False)),
        )


@dataclasses.dataclass
class Result:
    """What one check said, kept whole so a failure can be read rather than counted."""

    project: str
    step: str
    passed: bool
    output: str


def _run(command: tuple[str, ...], cwd: pathlib.Path) -> tuple[bool, str]:
    """Whether it succeeded, and everything it said, for a human to read."""
    passed, out, err = _spoke(command, cwd)
    return passed, "\n".join(part for part in (out, err) if part)


def _spoke(command: tuple[str, ...], cwd: pathlib.Path) -> tuple[bool, str, str]:
    """The same, with the streams kept apart: a warning on stderr must not glue itself onto an answer.

    Byte-code writing is off, because it is the last thing that would land in a project directory: the
    caches of the tools already go beside the environment, and a run has no business editing the
    repository it is measuring.
    """
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, env=environment)
    return completed.returncode == 0, completed.stdout.strip(), completed.stderr.strip()


def build(kind: str) -> pathlib.Path:
    """Build the package once and return the artefact to install everywhere.

    Built rather than installed from the source tree on purpose: an sdist that forgets a file, or a
    wheel missing `py.typed`, is invisible to every test that imports the repository.
    """
    if _BUILDS.exists():
        shutil.rmtree(_BUILDS)
    passed, output = _run(("uv", "build", f"--{kind}", "--out-dir", str(_BUILDS)), cwd=_ROOT)
    if not passed:
        raise SystemExit(f"building the {kind} failed:\n{output}")
    pattern = "*.whl" if kind == "wheel" else "*.tar.gz"
    return next(iter(sorted(_BUILDS.glob(pattern))))


def prepare(project: Project, artefact: pathlib.Path, ran: tuple[str, ...], keep: bool) -> pathlib.Path:
    """The environment the project's own tests and checkers run in.

    Not the one the extras are measured in: pytest and the checkers bring dependencies of their own.
    """
    environment = _ENVIRONMENTS / project.name
    packages = [
        _wanted(artefact, project.extras),
        *_TOOLS,
        *project.requires,
        # only the checkers that will actually run: installing an excluded one can still change how
        # the environment resolves, and it has no business doing that
        *(_TOOLS_BY_NAME[name] for name in ran),
    ]
    passed, output = _install(environment, packages)
    if not passed:
        # the half-built environment goes with it, unless environments are being kept: a failed install
        # is exactly the state somebody debugging wants to look at
        if not keep:
            shutil.rmtree(environment, ignore_errors=True)
        raise SystemExit(f"preparing the environment for {project.name} failed:\n{output}")
    return environment


def _python(environment: pathlib.Path) -> pathlib.Path:
    """The interpreter inside an environment, on either platform."""
    windows = environment / "Scripts" / "python.exe"
    return windows if windows.exists() else environment / "bin" / "python"


# what each extra brings, by distribution rather than import name, since a distribution is what an
# environment holds.  An optional dependency turned mandatory is invisible from inside the repository
_EXTRA_DISTRIBUTIONS: dict[str, tuple[str, ...]] = {
    "numpy": ("numpy",),
    "pandas": ("pandas",),
    "polars": ("polars",),
    "json": ("jsonpath-ng", "jsonschema", "referencing"),
    "inline": ("executing", "asttokens"),
    "allure": ("allure-pytest",),
    "behave": ("behave",),
}
_BUNDLES = {"data": ("numpy", "pandas", "polars")}


def _project() -> dict[str, object]:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def package_name() -> str:
    """What the package calls itself, canonicalised: hardcoding it would survive a rename in silence."""
    return _canonical(str(_project()["name"]))


def declared_extras() -> set[str]:
    """The extras the package itself offers, read from its own metadata rather than remembered here."""
    return {_canonical(extra) for extra in _project().get("optional-dependencies", {})}


def _canonical(name: str) -> str:
    """The one spelling of a name, folding case and every run of `-`, `_` and `.` the way packaging does."""
    return re.sub(r"[-_.]+", "-", name).lower()


def check_the_extras_table() -> Result:
    """The table here and the extras the package offers have to describe the same set, both ways.

    Once per run rather than per project: an extra nobody uses would otherwise sit undescribed, and a
    stale entry would start reporting a package as unwanted.
    """
    offered = declared_extras()
    described = set(_EXTRA_DISTRIBUTIONS) | set(_BUNDLES)
    complaints = []
    written = (
        described
        | {leaf for leaves in _BUNDLES.values() for leaf in leaves}
        | {name for names in _EXTRA_DISTRIBUTIONS.values() for name in names}
    )
    if uncanonical := sorted(name for name in written if name != _canonical(name)):
        complaints.append(f"table keys that are not canonical names: {', '.join(uncanonical)}")
    if undescribed := sorted(offered - described):
        complaints.append(f"offered by the package, not described here: {', '.join(undescribed)}")
    if stale := sorted(described - offered):
        complaints.append(f"described here, no longer offered: {', '.join(stale)}")
    # a bundle standing for an extra that does not exist, or for one nothing is recorded about, is the
    # same kind of stale: the expansion has to land on real leaves
    for bundle in _BUNDLES:
        try:
            leaves = _resolved((bundle,))
        except RecursionError:
            complaints.append(f"bundle {bundle} expands into itself")
            continue
        if broken := sorted(leaf for leaf in leaves if leaf not in offered or leaf not in _EXTRA_DISTRIBUTIONS):
            complaints.append(f"bundle {bundle} expands onto something unusable: {', '.join(broken)}")
    return Result("corpus", "extras table", not complaints, "; ".join(complaints))


def check_the_baseline(artefact: pathlib.Path, keep: bool) -> tuple[Result, dict[str, list[dict[str, object]]]]:
    """What the package installs with no extras, and whether that is what it promised to install.

    Two answers from one environment: the check, and the floor the per-project checks measure against.
    A dependency that quietly became mandatory can only show up here, because it would be in every
    environment and comparing environments to each other would never see it.
    """
    environment = _ENVIRONMENTS / "baseline"
    try:
        # `packaging` alone, not the rest of the tools.  `pytest` brings a tree of its own, and anything
        # inside it would become part of the floor and hide a real leak above it.  The environment that
        # runs the tests does install pytest, and it is a different environment for exactly this reason
        passed, output = _install(environment, [str(artefact), _INSTRUMENT])
        if not passed:
            raise SystemExit(f"installing the package without extras failed:\n{output}")
        installed = _inventory_of(environment)

        entitled = {package_name(), *_declared_dependencies(), _named(_INSTRUMENT)}
        promised = {name for start in entitled for name in _reachable_from(start, installed)} | entitled
        unpromised = sorted(name for name in installed if name not in promised)
        # and both other directions.  A dependency declared in `pyproject.toml` that this file does not
        # know about is a change nobody agreed to, and a promise kept here after the dependency was
        # dropped is a stale rule that would quietly excuse it coming back
        written = {_named(requirement) for requirement in _project().get("dependencies", [])}
        unagreed = sorted(written - _PROMISED_DEPENDENCIES)
        abandoned = sorted(_PROMISED_DEPENDENCIES - written)
        return (
            Result(
                "corpus",
                "plain install",
                not (unpromised or unagreed or abandoned),
                "; ".join(
                    part
                    for part in (
                        f"a plain install holds what nobody declared: {', '.join(unpromised)}" if unpromised else "",
                        f"runtime dependencies nobody agreed to: {', '.join(unagreed)}" if unagreed else "",
                        f"promised here, no longer declared: {', '.join(abandoned)}" if abandoned else "",
                    )
                    if part
                ),
            ),
            installed,
        )
    finally:
        if not keep:
            shutil.rmtree(environment, ignore_errors=True)


def _named(requirement: str) -> str:
    """The distribution a requirement string names, canonicalised: `packaging>=24,<26` is `packaging`."""
    return _canonical(re.split(r"[\s\[<>=!;~]", requirement.strip(), maxsplit=1)[0])


# written here rather than read from `pyproject.toml`, which would make the check circular: a
# dependency added by mistake would arrive already declared and the plain install would stay green
_PROMISED_DEPENDENCIES = frozenset({"typing-extensions"})


def _declared_dependencies() -> set[str]:
    """What a plain install is entitled to hold beyond the package itself."""
    written = {_named(requirement) for requirement in _project().get("dependencies", [])}
    return written | _PROMISED_DEPENDENCIES


def _reachable_from(start: str, installed: dict[str, list[dict[str, object]]]) -> set[str]:
    """Everything reachable from one distribution through requirements that always apply."""
    found: set[str] = set()
    pending = [start]
    while pending:
        name = pending.pop()
        if name in found or name not in installed:
            continue
        found.add(name)
        pending.extend(str(requirement["name"]) for requirement in installed[name] if requirement["always"])
    return found


def _inventory_of(environment: pathlib.Path) -> dict[str, list[dict[str, object]]]:
    passed, answer, complaint = _spoke((str(_python(environment)), str(_CORPUS / "_inventory.py")), cwd=_CORPUS)
    if not passed:
        raise SystemExit(f"reading the environment failed:\n{complaint or answer}")
    return json.loads(answer)


def check_extras(
    project: Project, artefact: pathlib.Path, baseline: dict[str, list[dict[str, object]]], keep: bool
) -> Result:
    """Assert that the optional dependencies present are exactly the ones this project asked for.

    Measured in an environment holding the built package and nothing else: the test environment also has
    pytest and the checkers, which pull in `numpy` and friends transitively.

    Compared against the table *and* the baseline install, so a package absent from a plain install and
    reachable from no requested extra is a leak whether or not anybody wrote it down.
    """
    try:
        expected_leaves = _resolved(project.extras)
    except RecursionError as cycle:
        return Result(project.name, "extras", False, f"a bundle expands into itself: {cycle}")

    unknown = sorted(set(project.extras) - declared_extras())
    undescribed = sorted(extra for extra in expected_leaves if extra not in _EXTRA_DISTRIBUTIONS)
    if unknown or undescribed:
        return Result(
            project.name,
            "extras",
            False,
            "; ".join(
                part
                for part in (
                    f"asks for extras the package does not offer: {', '.join(unknown)}" if unknown else "",
                    f"extras with no distributions recorded for them: {', '.join(undescribed)}" if undescribed else "",
                )
                if part
            ),
        )

    environment = _ENVIRONMENTS / f"{project.name}-extras"
    try:
        passed, output = _install(environment, [_wanted(artefact, project.extras), _INSTRUMENT])
        if not passed:
            return Result(project.name, "extras", False, output)
        installed = _inventory_of(environment)

        if unreadable := sorted(
            f"{name}: {requirement['unreadable']}"
            for name, requirements in installed.items()
            for requirement in requirements
            if requirement.get("unreadable")
        ):
            return Result(project.name, "extras", False, f"requirements nobody could read: {'; '.join(unreadable)}")

        wanted = {_canonical(name) for extra in expected_leaves for name in _EXTRA_DISTRIBUTIONS.get(extra, ())}
        entitled = _reachable(installed, set(project.extras) | expected_leaves)

        complaints = []
        if missing := sorted(name for name in wanted if name not in installed):
            complaints.append(f"asked for but not installed: {', '.join(missing)}")
        # anything here that the plain install does not have, and that nothing requested can reach
        if stray := sorted(name for name in installed if name not in baseline and name not in entitled):
            complaints.append(f"installed without being asked for: {', '.join(stray)}")
        return Result(project.name, "extras", not complaints, "; ".join(complaints))
    finally:
        if not keep:
            shutil.rmtree(environment, ignore_errors=True)


def _reachable(installed: dict[str, list[dict[str, object]]], extras: set[str]) -> set[str]:
    """Everything the environment is entitled to hold, walked as `(distribution, extras asked of it)`.

    The pair is the point: reaching `pandas` says nothing about `pandas[performance]`, and switching on
    every extra of every dependency would make any optional package look legitimate.
    """
    entitled: set[str] = set()
    seen: set[tuple[str, tuple[str, ...]]] = set()
    pending = [(package_name(), tuple(sorted(extras)))]
    while pending:
        name, asked = pending.pop()
        if (name, asked) in seen or name not in installed:
            continue
        seen.add((name, asked))
        entitled.add(name)
        for requirement in installed[name]:
            applies = requirement["always"] or bool(set(requirement["applies"]) & set(asked))
            if applies and requirement["name"]:
                pending.append((requirement["name"], tuple(sorted(requirement["wants"]))))
    return entitled


def _resolved(extras: tuple[str, ...], seen: frozenset[str] = frozenset()) -> set[str]:
    """The leaf extras really in play, with every bundle replaced by what it stands for, recursively."""
    resolved: set[str] = set()
    for extra in extras:
        if extra not in _BUNDLES:
            resolved.add(extra)
        elif extra in seen:
            raise RecursionError(extra)
        else:
            resolved |= _resolved(_BUNDLES[extra], seen | {extra})
    return resolved


def _wanted(artefact: pathlib.Path, extras: tuple[str, ...]) -> str:
    return f"{artefact}[{','.join(extras)}]" if extras else str(artefact)


def _install(environment: pathlib.Path, packages: list[str]) -> tuple[bool, str]:
    """A fresh environment holding exactly `packages`, on the Python a consumer would use."""
    shutil.rmtree(environment, ignore_errors=True)
    version = ("--python", _CONSUMER_PYTHON) if _CONSUMER_PYTHON else ()
    passed, output = _run(("uv", "venv", *version, str(environment)), cwd=_CORPUS)
    if not passed:
        return False, output
    return _run(("uv", "pip", "install", "--python", str(_python(environment)), *packages), cwd=_CORPUS)


def versions(environment: pathlib.Path, ran: tuple[str, ...]) -> dict[str, str]:
    """What this environment resolved the package and the tools that ran to.

    Per project, because two projects can resolve a checker differently, and only for the checkers that
    ran, so a `--checkers mypy` artefact does not claim pyright judged anything.
    """
    script = (
        "import json;from importlib.metadata import distributions;"
        "print(json.dumps({d.metadata['Name']: d.version for d in distributions() if d.metadata['Name']}))"
    )
    passed, answer, _ = _spoke((str(_python(environment)), "-c", script), cwd=_CORPUS)
    if not passed:
        return {}
    found = dict(sorted(json.loads(answer).items()))
    if package_name() not in {_canonical(name) for name in found}:
        return {}
    wanted = _RECORDED | set(ran) | {package_name()}
    return {name: version for name, version in found.items() if _canonical(name) in wanted}


def check(project: Project, environment: pathlib.Path, wanted: tuple[str, ...]) -> list[Result]:
    """Run the project's own tests, then every checker it asks for."""
    interpreter = _python(environment)
    cache = environment / "caches"
    # `-p no:cacheprovider` for the same reason: pytest writes `.pytest_cache` into the directory it
    # runs in, and the project directory belongs to the repository rather than to this run
    running = (str(interpreter), "-m", "pytest", "-q", "-p", "no:cacheprovider")
    results = [Result(project.name, "pytest", *_run(running, cwd=project.path))]
    for name in project.checkers:
        if name not in wanted:
            continue
        module, *arguments = (_STRICT if project.mypy_strict else _CHECKERS).get(name, _CHECKERS[name])
        spelled = [argument.format(python=interpreter, cache=cache) for argument in arguments]
        results.append(Result(project.name, name, *_run((str(interpreter), "-m", module, *spelled), cwd=project.path)))
    return results


def report(results: list[Result]) -> int:
    """Print one line per check, then everything that failed, and answer with an exit code."""
    for result in results:
        print(f"  {'ok  ' if result.passed else 'FAIL'}  {result.project:28} {result.step}")
    failures = [result for result in results if not result.passed]
    for failure in failures:
        print(f"\n=== {failure.project}: {failure.step} ===\n{failure.output}")
    print(f"\n{len(results) - len(failures)}/{len(results)} checks passed")
    return 1 if failures else 0


def _discard(*directories: pathlib.Path) -> None:
    """Remove this run's directories, and their shared parent once the last run has left it empty."""
    for directory in directories:
        shutil.rmtree(directory, ignore_errors=True)
        with contextlib.suppress(OSError):
            directory.parent.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="kind", default="wheel", choices=("wheel", "sdist"))
    parser.add_argument("--only", nargs="+", default=None, help="project names, all of them by default")
    parser.add_argument("--checkers", nargs="*", default=tuple(_CHECKERS), choices=tuple(_CHECKERS))
    parser.add_argument("--keep", action="store_true", help="leave the environments in place afterwards")
    parser.add_argument("--python", default=None, help="the Python a consumer would use, e.g. 3.10")
    parser.add_argument("--json", type=pathlib.Path, default=None, help="also write the results as JSON")
    arguments = parser.parse_args()

    global _CONSUMER_PYTHON
    _CONSUMER_PYTHON = arguments.python

    projects = [Project.read(path) for path in sorted(_PROJECTS.iterdir()) if (path / "corpus.toml").exists()]
    if arguments.only:
        unknown = sorted(set(arguments.only) - {project.name for project in projects})
        if unknown:
            raise SystemExit(f"no such project: {', '.join(unknown)}")
        projects = [project for project in projects if project.name in arguments.only]
    if not projects:
        raise SystemExit("no projects matched")

    results: list[Result] = []
    resolved: dict[str, dict[str, str]] = {}
    try:
        artefact = build(arguments.kind)
        print(f"testing {artefact.name}\n")

        results.append(check_the_extras_table())
        plain, baseline = check_the_baseline(artefact, arguments.keep)
        results.append(plain)
        for project in projects:
            results.append(check_extras(project, artefact, baseline, arguments.keep))
            ran = tuple(name for name in project.checkers if name in arguments.checkers)
            environment = prepare(project, artefact, ran, arguments.keep)
            try:
                recorded = versions(environment, ran)
                resolved[project.name] = recorded
                results.append(
                    Result(project.name, "versions", bool(recorded), "" if recorded else "could not read the versions")
                )
                results.extend(check(project, environment, ran))
            finally:
                if not arguments.keep:
                    shutil.rmtree(environment, ignore_errors=True)
    finally:
        if not arguments.keep:
            _discard(_BUILDS, _ENVIRONMENTS)
    if arguments.json:
        arguments.json.parent.mkdir(parents=True, exist_ok=True)
        report_data = {
            "installed_from": arguments.kind,
            "versions": resolved,
            "results": [dataclasses.asdict(result) for result in results],
        }
        arguments.json.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    return report(results)


if __name__ == "__main__":
    sys.exit(main())
