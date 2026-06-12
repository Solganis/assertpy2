import asyncio
import threading

import pytest

from assertpy2 import assert_that, soft_assertions, soft_fail
from assertpy2.async_assertions import AsyncAssertionBuilder


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
        for t in threads:
            t.start()
        for t in threads:
            t.join()

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
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert_that(errors_from_threads).is_length(2)
        for thread_id, error_msg in errors_from_threads:
            assert_that(error_msg).contains(f"thread {thread_id}")

    def test_nested_soft_assertions_still_work(self):
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_that(1).is_equal_to(2)
            with soft_assertions():
                assert_that(3).is_equal_to(4)
            assert_that(5).is_equal_to(6)
