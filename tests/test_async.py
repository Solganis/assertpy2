import asyncio
import itertools
import logging
import threading
from io import StringIO

import pytest

import assertpy2.async_assertions as aa
from assertpy2 import (
    AssertionFailure,
    PollSample,
    WarningLoggingAdapter,
    assert_that,
    assert_warn,
    soft_assertions,
    soft_fail,
)
from assertpy2.async_assertions import _RETRIES, AsyncAssertionBuilder, _PollRecorder, _summarize


class TestEventuallyBasic:
    def test_value_converges(self):
        counter = {"n": 0}

        def get_count():
            counter["n"] += 1
            return counter["n"]

        result = asyncio.run(assert_that(get_count).eventually(timeout=2, interval=0.05).is_equal_to(3))
        assert_that(result).is_not_none()

    def test_immediate_match(self):
        asyncio.run(assert_that(lambda: 42).eventually(timeout=1, interval=0.05).is_equal_to(42))

    def test_timeout_raises(self):
        with pytest.raises(AssertionError, match="not met after"):
            asyncio.run(assert_that(lambda: 0).eventually(timeout=0.2, interval=0.05).is_equal_to(999))

    def test_timeout_message_includes_last_failure(self):
        with pytest.raises(AssertionError, match="to be equal to"):
            asyncio.run(assert_that(lambda: 1).eventually(timeout=0.15, interval=0.05).is_equal_to(999))

    def test_non_callable_raises_type_error(self):
        with pytest.raises(TypeError, match="val must be callable"):
            assert_that(42).eventually()


class TestEventuallyWithAsyncCallable:
    def test_async_callable(self):
        counter = {"n": 0}

        async def get_count():
            counter["n"] += 1
            return counter["n"]

        asyncio.run(assert_that(get_count).eventually(timeout=2, interval=0.05).is_equal_to(3))

    def test_async_callable_timeout(self):
        async def always_zero():
            return 0

        with pytest.raises(AssertionError, match="not met after"):
            asyncio.run(assert_that(always_zero).eventually(timeout=0.15, interval=0.05).is_equal_to(1))

    def test_sync_callable_returning_awaitable(self):
        async def compute():
            return 42

        # a sync callable that returns a coroutine must still be awaited before asserting
        asyncio.run(assert_that(lambda: compute()).eventually(timeout=1, interval=0.05).is_equal_to(42))


class TestEventuallyChaining:
    def test_within(self):
        counter = {"n": 0}

        def get_count():
            counter["n"] += 1
            return counter["n"]

        builder = assert_that(get_count).eventually()
        assert_that(builder).is_instance_of(AsyncAssertionBuilder)
        asyncio.run(builder.within(2).every(0.05).is_equal_to(3))

    def test_various_assertions(self):
        counter = {"n": 0}

        def get_value():
            counter["n"] += 1
            return counter["n"]

        asyncio.run(assert_that(get_value).eventually(timeout=2, interval=0.05).is_greater_than(3))

    def test_string_assertion(self):
        states = iter(["loading", "loading", "ready"])

        def get_status():
            return next(states, "ready")

        asyncio.run(assert_that(get_status).eventually(timeout=1, interval=0.05).is_equal_to("ready"))


class TestEventuallyPrivateAttrs:
    def test_private_attr_raises_attribute_error(self):
        builder = assert_that(lambda: 1).eventually()
        with pytest.raises(AttributeError):
            _ = builder._nonexistent


class TestEventuallyIgnoring:
    def test_ignored_exception_is_retried(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("not ready")
            return 42

        asyncio.run(assert_that(probe).eventually(timeout=2, interval=0.05, ignoring=ConnectionError).is_equal_to(42))
        assert_that(calls["n"]).is_equal_to(3)

    def test_exception_not_ignored_propagates_immediately(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            raise ConnectionError("not ready")

        with pytest.raises(ConnectionError, match="not ready"):
            asyncio.run(assert_that(probe).eventually(timeout=2, interval=0.05).is_equal_to(42))
        assert_that(calls["n"]).is_equal_to(1)

    def test_other_exception_still_propagates(self):
        def probe():
            raise KeyError("missing")

        with pytest.raises(KeyError, match="missing"):
            asyncio.run(
                assert_that(probe).eventually(timeout=1, interval=0.05, ignoring=ConnectionError).is_equal_to(42)
            )

    def test_ignoring_tuple_of_exceptions(self):
        errors = iter([ConnectionError("boot"), TimeoutError("slow")])

        def probe():
            error = next(errors, None)
            if error is not None:
                raise error
            return "ready"

        asyncio.run(
            assert_that(probe)
            .eventually(timeout=2, interval=0.05, ignoring=(ConnectionError, TimeoutError))
            .is_equal_to("ready")
        )

    def test_ignored_exception_until_timeout_reports_last_failure(self):
        def probe():
            raise ConnectionError("still booting")

        with pytest.raises(AssertionError, match=r"not met after .* ConnectionError\('still booting'\)"):
            asyncio.run(assert_that(probe).eventually(timeout=0.15, interval=0.05, ignoring=ConnectionError).is_none())

    def test_ignoring_chainable_on_builder(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("not ready")
            return "ok"

        asyncio.run(assert_that(probe).eventually().within(2).every(0.05).ignoring(ConnectionError).is_equal_to("ok"))

    def test_mixed_exception_and_assertion_failures(self):
        states = iter([ConnectionError("boot"), "loading", "ready"])

        def probe():
            state = next(states, "ready")
            if isinstance(state, Exception):
                raise state
            return state

        asyncio.run(
            assert_that(probe).eventually(timeout=2, interval=0.05, ignoring=ConnectionError).is_equal_to("ready")
        )

    def test_async_probe_with_ignored_exception(self):
        calls = {"n": 0}

        async def probe():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("not ready")
            return 7

        asyncio.run(assert_that(probe).eventually(timeout=2, interval=0.05, ignoring=ConnectionError).is_equal_to(7))

    def test_ignoring_rejects_non_exception_type(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually(ignoring=42)

    def test_ignoring_rejects_non_exception_in_tuple(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually(ignoring=(ValueError, "oops"))

    def test_ignoring_rejects_base_exception_only_classes(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually(ignoring=KeyboardInterrupt)

    def test_ignoring_method_rejects_non_exception_type(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually().ignoring(int)


class TestEventuallyFailureModes:
    """Polling always retries on hard failures; the final timeout failure honors the builder's mode."""

    def test_soft_collects_timeout_failure_and_continues(self):
        async def scenario():
            with soft_assertions():
                await assert_that(lambda: 1).eventually(timeout=0.15, interval=0.05).is_equal_to(2)
                assert_that("after-eventually-marker").is_equal_to("other")

        with pytest.raises(AssertionError) as exc_info:
            asyncio.run(scenario())
        text = str(exc_info.value)
        assert_that(text).contains("soft assertion failures")
        assert_that(text).contains("not met after")
        assert_that(text).contains("after-eventually-marker")

    def test_soft_passing_eventually_collects_nothing(self):
        async def scenario():
            with soft_assertions():
                await assert_that(lambda: 42).eventually(timeout=1, interval=0.05).is_equal_to(42)

        asyncio.run(scenario())

    def test_soft_timeout_message_keeps_single_description_prefix(self):
        async def scenario():
            with soft_assertions():
                await (
                    assert_that(lambda: 1)
                    .described_as("probe-label")
                    .eventually(timeout=0.15, interval=0.05)
                    .is_equal_to(2)
                )

        with pytest.raises(AssertionError) as exc_info:
            asyncio.run(scenario())
        assert_that(str(exc_info.value).count("[probe-label]")).is_equal_to(1)

    def test_warn_logs_timeout_failure_without_raising(self):
        capture = StringIO()
        logger = logging.getLogger("capture-eventually-warn")
        logger.addHandler(logging.StreamHandler(capture))
        adapted = WarningLoggingAdapter(logger, None)

        async def scenario():
            await assert_warn(lambda: 1, logger=adapted).eventually(timeout=0.15, interval=0.05).is_equal_to(2)

        asyncio.run(scenario())
        assert_that(capture.getvalue()).contains("not met after").contains("to be equal to <2>")


class TestPollRecorder:
    """Unit coverage of collapsing and first+last retention, deterministic via direct record() calls."""

    def test_identical_polls_collapse_into_repeats(self):
        recorder = _PollRecorder()
        for _ in range(4):
            recorder.record(elapsed=0.1, outcome="fail", value=1, detail="same")
        trace = recorder.build(elapsed=1.0)
        assert_that(trace.samples).is_length(1)
        assert_that(trace.samples[0].repeats).is_equal_to(4)
        assert_that(trace.total_polls).is_equal_to(4)

    def test_collapse_applies_inside_the_tail_window(self):
        recorder = _PollRecorder(head=1, tail=3)
        recorder.record(elapsed=0.0, outcome="fail", value=0, detail="d0")
        recorder.record(elapsed=0.1, outcome="fail", value=1, detail="d1")
        recorder.record(elapsed=0.2, outcome="fail", value=1, detail="d1")
        trace = recorder.build(elapsed=1.0)
        assert_that(trace.samples).is_length(2)
        assert_that(trace.samples[1].repeats).is_equal_to(2)
        assert_that(trace.samples[1].elapsed).is_equal_to(0.1)

    def test_retention_keeps_first_and_last_and_counts_dropped(self):
        recorder = _PollRecorder(head=2, tail=3)
        for index in range(10):
            recorder.record(elapsed=float(index), outcome="fail", value=index, detail=f"d{index}")
        trace = recorder.build(elapsed=10.0)
        assert_that([sample.value for sample in trace.samples]).is_equal_to([0, 1, 7, 8, 9])
        assert_that(trace.dropped).is_equal_to(5)
        assert_that(trace.total_polls).is_equal_to(10)

    def test_error_and_fail_outcomes_do_not_collapse_together(self):
        recorder = _PollRecorder()
        recorder.record(elapsed=0.0, outcome="error", value=None, detail="ConnectionError('x')")
        recorder.record(elapsed=0.1, outcome="fail", value=None, detail="ConnectionError('x')")
        assert_that(recorder.build(elapsed=1.0).samples).is_length(2)


class TestSummaryUnderWindowOverflow:
    """The summary reads a bounded window, so a long poll drops middle samples before classifying."""

    def _summary_of(self, values):
        recorder = _PollRecorder()
        for index, value in enumerate(values):
            recorder.record(elapsed=index * 0.1, outcome="fail", value=value, detail=f"got {value}")
        trace = recorder.build(elapsed=len(values) * 0.1)
        assert_that(trace.dropped).is_greater_than(0)  # the guard: without a drop this proves nothing
        return trace.summary

    def test_a_long_monotonic_walk_is_not_mistaken_for_a_cycle(self):
        assert_that(self._summary_of([f"step{i}" for i in range(40)])).does_not_contain("cycles")

    def test_a_long_monotonic_walk_with_plateaus_is_not_mistaken_for_a_cycle(self):
        assert_that(self._summary_of([f"step{i // 4}" for i in range(120)])).does_not_contain("cycles")

    def test_a_cycle_is_still_detected_after_samples_are_dropped(self):
        values = ["up" if i % 2 else "down" for i in range(40)]
        assert_that(self._summary_of(values)).is_equal_to("value cycles between 2 states across 40 polls")


class TestTraceSummary:
    def _sample(self, **overrides):
        base = {"elapsed": 0.0, "outcome": "fail", "value": 1, "detail": "d", "repeats": 1}
        base.update(overrides)
        return PollSample(**base)

    def _summary(self, samples, total_polls, elapsed):
        fail_polls = sum(sample.repeats for sample in samples if sample.outcome == "fail")
        error_polls = sum(sample.repeats for sample in samples if sample.outcome == "error")
        return _summarize(samples, total_polls, elapsed, fail_polls, error_polls)

    def test_all_errors_single_type(self):
        samples = [self._sample(outcome="error", detail="ConnectionError('boot')", value=None)]
        assert_that(self._summary(samples, 7, 5.0)).is_equal_to("probe raised ConnectionError on all 7 polls")

    def test_all_errors_mixed_types(self):
        samples = [
            self._sample(outcome="error", detail="ConnectionError('boot')", value=None),
            self._sample(outcome="error", detail="TimeoutError('slow')", value=None, elapsed=0.5),
        ]
        assert_that(self._summary(samples, 4, 5.0)).is_equal_to("probe raised exceptions on all 4 polls")

    def test_recovered_then_stable(self):
        samples = [
            self._sample(outcome="error", detail="ConnectionError('boot')", value=None, repeats=3),
            self._sample(elapsed=1.5, value={"s": 1}),
        ]
        assert_that(self._summary(samples, 5, 5.0)).is_equal_to(
            "probe recovered after 3 raising polls; value then never changed"
        )

    def test_recovered_then_changing(self):
        samples = [
            self._sample(outcome="error", detail="ConnectionError('boot')", value=None),
            self._sample(elapsed=1.0, value={"s": 1}),
            self._sample(elapsed=2.0, value={"s": 2}),
        ]
        assert_that(self._summary(samples, 3, 5.0)).is_equal_to(
            "probe recovered after 1 raising poll; value then changed 1 time"
        )

    def test_value_never_changed(self):
        samples = [self._sample(repeats=9)]
        assert_that(self._summary(samples, 9, 5.0)).is_equal_to("value unchanged across 9 polls")

    def test_value_changed_reports_last_change(self):
        samples = [
            self._sample(elapsed=0.0, value=1),
            self._sample(elapsed=1.0, value=2),
            self._sample(elapsed=3.5, value=3),
        ]
        assert_that(self._summary(samples, 3, 5.0)).is_equal_to(
            "value changed 2 times; last change 1.5s before the deadline"
        )

    def test_a_repeating_value_is_reported_as_a_cycle(self):
        # "changed 4 times" reads like slow progress; the probe is really stuck alternating
        samples = [self._sample(elapsed=float(i), value="up" if i % 2 else "down") for i in range(5)]
        assert_that(self._summary(samples, 5, 5.0)).is_equal_to("value cycles between 2 states across 5 polls")

    def test_returning_to_an_earlier_value_once_is_a_cycle(self):
        samples = [
            self._sample(elapsed=0.0, value=1),
            self._sample(elapsed=1.0, value=2),
            self._sample(elapsed=2.0, value=3),
            self._sample(elapsed=3.0, value=1),
        ]
        assert_that(self._summary(samples, 4, 5.0)).is_equal_to("value cycles between 3 states across 4 polls")

    def test_steady_progress_is_not_reported_as_a_cycle(self):
        # the guard that matters: a value walking through new states must keep the last-change wording
        samples = [self._sample(elapsed=float(i), value=i) for i in range(4)]
        assert_that(self._summary(samples, 4, 5.0)).is_equal_to(
            "value changed 3 times; last change 2.0s before the deadline"
        )

    def test_dropped_fail_samples_not_reported_as_all_raised(self):
        # fail_polls counts every poll, so even when the retained window holds only error samples the
        # summary must not claim the probe raised on all polls (some polls returned a value and failed)
        error_only = [self._sample(outcome="error", detail="ConnectionError('x')", value=None)]
        summary = _summarize(error_only, 30, 5.0, fail_polls=4, error_polls=26)
        assert_that(summary).does_not_contain("on all")
        assert_that(summary).contains("recovered after 26 raising polls")


class TestEventuallyTrace:
    def test_timeout_failure_carries_the_trace(self):
        states = iter([ConnectionError("boot"), {"s": "PENDING"}])

        def probe():
            state = next(states, {"s": "PENDING"})
            if isinstance(state, Exception):
                raise state
            return state

        async def scenario():
            await (
                assert_that(probe)
                .eventually(timeout=1.0, interval=0.01, ignoring=ConnectionError)
                .is_equal_to({"s": "PAID"})
            )

        with pytest.raises(AssertionFailure) as exc_info:
            asyncio.run(scenario())
        trace = exc_info.value.trace
        assert_that(trace).is_not_none()
        assert_that(trace.samples[0].outcome).is_equal_to("error")
        assert_that(trace.samples[0].value).is_none()
        assert_that(trace.samples[1].outcome).is_equal_to("fail")
        assert_that(trace.samples[1].value).is_equal_to({"s": "PENDING"})
        assert_that(trace.total_polls).is_greater_than_or_equal_to(2)
        assert_that(str(exc_info.value)).contains("(probe recovered after 1 raising poll;")

    def test_samples_are_point_in_time_snapshots_of_a_mutating_probe(self):
        live = {"step": 0}

        def probe():
            live["step"] += 1
            return live

        async def scenario():
            await assert_that(probe).eventually(timeout=1.0, interval=0.01).is_equal_to({"step": -1})

        with pytest.raises(AssertionFailure) as exc_info:
            asyncio.run(scenario())
        samples = exc_info.value.trace.samples
        assert_that(len(samples)).is_greater_than_or_equal_to(2)
        assert_that(samples[0].value).is_not_equal_to(samples[-1].value)
        assert_that(samples[0].value).is_equal_to({"step": 1})

    def test_unchanged_value_produces_unchanged_summary(self):
        async def scenario():
            await assert_that(lambda: 7).eventually(timeout=0.15, interval=0.03).is_equal_to(8)

        with pytest.raises(AssertionFailure, match=r"\(value unchanged across \d+ polls\)"):
            asyncio.run(scenario())

    def test_soft_mode_message_carries_the_summary(self):
        async def scenario():
            with soft_assertions():
                await assert_that(lambda: 7).eventually(timeout=0.15, interval=0.03).is_equal_to(8)

        with pytest.raises(AssertionError) as exc_info:
            asyncio.run(scenario())
        assert_that(str(exc_info.value)).contains("value unchanged across")


class TestContextVarsIsolation:
    def test_soft_assertions_thread_isolation(self):
        errors_from_threads = {}

        def thread_func(thread_id):
            try:
                with soft_assertions():
                    assert_that(f"thread-{thread_id}-marker").is_equal_to("wrong")
            except AssertionError as exc:
                errors_from_threads[thread_id] = str(exc)

        threads = [threading.Thread(target=thread_func, args=(i,)) for i in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert_that(errors_from_threads).is_length(3)
        for thread_id, error_msg in errors_from_threads.items():
            assert_that(error_msg).contains(f"thread-{thread_id}-marker")
            other_ids = [i for i in range(3) if i != thread_id]
            for other_id in other_ids:
                assert_that(error_msg).does_not_contain(f"thread-{other_id}-marker")

    def test_soft_assertions_async_isolation(self):
        async def task_func(task_id):
            with soft_assertions():
                assert_that(task_id).is_equal_to(-1)

        async def run_tasks():
            tasks = [asyncio.create_task(task_func(i)) for i in range(3)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        results = asyncio.run(run_tasks())
        assert_that(results).is_length(3)
        for i, result in enumerate(results):
            assert_that(result).is_instance_of(AssertionError)
            assert_that(str(result)).contains(str(i))

    def test_soft_fail_thread_isolation(self):
        errors_from_threads = []

        def thread_func(thread_id):
            try:
                with soft_assertions():
                    soft_fail(f"error from thread {thread_id}")
            except AssertionError as exc:
                errors_from_threads.append((thread_id, str(exc)))

        threads = [threading.Thread(target=thread_func, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert_that(errors_from_threads).is_length(2)
        for thread_id, error_msg in errors_from_threads:
            assert_that(error_msg).contains(f"thread {thread_id}")

    def test_nested_soft_assertions_still_work(self):
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_that(1).is_equal_to(2)
            with soft_assertions():
                assert_that(3).is_equal_to(4)
            assert_that(5).is_equal_to(6)


class TestRetryCollection:
    """A poll that converged late is recorded, so the plugin can name it after the run."""

    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch):
        monkeypatch.setattr(aa, "_COLLECT_RETRIES", True)
        _RETRIES.clear()
        yield
        _RETRIES.clear()

    def test_nothing_is_collected_without_the_plugin(self, monkeypatch):
        # the plugin is the only consumer: off pytest (unittest, a script) the list would grow for the
        # whole life of the process with nobody to drain it
        monkeypatch.setattr(aa, "_COLLECT_RETRIES", False)
        states = itertools.chain(["PENDING"] * 2, itertools.repeat("READY"))
        assert_that(lambda: next(states)).eventually_sync(timeout=2, interval=0.02).is_equal_to("READY")
        assert_that(_RETRIES).is_empty()

    def test_a_retried_poll_is_recorded_with_its_budget(self):
        states = itertools.chain(["PENDING"] * 2, itertools.repeat("READY"))
        assert_that(lambda: next(states)).eventually_sync(timeout=2, interval=0.02).is_equal_to("READY")
        assert_that(_RETRIES).is_length(1)
        attempts, elapsed, budget = _RETRIES[0]
        assert_that(attempts).is_equal_to(3)
        assert_that(budget).is_equal_to(2)
        assert_that(elapsed).is_greater_than(0)

    def test_a_first_attempt_pass_records_nothing(self):
        assert_that(lambda: "READY").eventually_sync(timeout=2, interval=0.02).is_equal_to("READY")
        assert_that(_RETRIES).is_empty()

    def test_the_async_path_records_too(self):
        states = itertools.chain(["PENDING"] * 2, itertools.repeat("READY"))
        asyncio.run(assert_that(lambda: next(states)).eventually(timeout=2, interval=0.02).is_equal_to("READY"))
        assert_that(_RETRIES).is_length(1)

    def test_a_timeout_records_nothing(self):
        # it never converged, so it is a failure with a trace, not a poll that nearly made it
        with pytest.raises(AssertionError):
            assert_that(lambda: "PENDING").eventually_sync(timeout=0.1, interval=0.02).is_equal_to("READY")
        assert_that(_RETRIES).is_empty()
