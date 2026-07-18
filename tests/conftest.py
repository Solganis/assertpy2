import pytest

from assertpy2 import errors as _errors
from assertpy2 import snapshot as _snapshot


@pytest.fixture(autouse=True)
def _plain_messages(monkeypatch):
    """Pin the diff off the failure message for the suite.

    The suite runs with the plugin disabled (``-p no:assertpy2``), so the diff-in-message default (on)
    would append the structured diff to every ``str(exc)`` and break the exact-message assertions.  Off
    here it mirrors what plugin-on users see, where the plugin renders the diff as its own report section
    instead; the off-pytest diff-in-message path has its own targeted tests that opt back in.
    """
    monkeypatch.setattr(_errors, "_RENDER_DIFF_IN_MESSAGE", False)


@pytest.fixture(autouse=True)
def _snapshot_isolation(monkeypatch):
    """Per-test snapshot isolation.

    Baseline CI mode off: many tests intentionally *create* snapshots in ``tmp_path``; GitHub Actions
    sets ``CI=true``, which would auto-enable snapshot CI mode and turn those creations into failures.
    The tri-state flag has the highest precedence, so ``False`` forces CI mode off regardless of ambient
    env; the CI-mode tests opt back in explicitly.  Also restore the custom-serializer registry so a
    test that registers a serializer does not leak into later tests.
    """
    monkeypatch.setattr(_snapshot, "_CI_MODE", False)
    saved_serializers = list(_snapshot._SERIALIZERS)
    saved_touched = set(_snapshot._TOUCHED)
    yield
    _snapshot._SERIALIZERS[:] = saved_serializers
    _snapshot._TOUCHED.clear()
    _snapshot._TOUCHED.update(saved_touched)
