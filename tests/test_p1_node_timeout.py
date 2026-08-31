"""
tests/test_p1_node_timeout.py
-------------------------------
Tests for Priority 1D (preemptive timeout enforcement),
3D (max_retries semantics), and 3F (cancellable retry sleep).
"""
from __future__ import annotations

import threading
import time

import pytest

from pyasl.pipeline.node import Node, NodeStatus
from pyasl.pipeline.exceptions.errors import NodeTimeoutError, NodeAbortedError


# ======================================================================
# 1D — Preemptive timeout enforcement
# ======================================================================

class TestPreemptiveTimeout:
    """Verify that timeout actually kills a hung function."""

    def test_timeout_kills_hung_function(self):
        """A function that sleeps forever should be killed by the timeout."""
        # Use an event so we can release the background thread after test
        hang_event = threading.Event()

        def hung_function(payload):
            hang_event.wait(timeout=30)  # wait up to 30s but we'll release it
            return {"status": "success"}

        node = Node(
            node_id="timeout_test",
            function_name="hung",
            timeout_seconds=0.5,
            max_retries=0,
        )
        node.function = hung_function

        start = time.monotonic()
        result = node.execute({})
        elapsed = time.monotonic() - start

        # Release the background thread so it cleans up
        hang_event.set()

        assert node.status == NodeStatus.TIMED_OUT
        assert result["timed_out"] is True
        # Should have returned in ~0.5s, not 30s
        assert elapsed < 10.0, f"Timeout took {elapsed}s — should be ~0.5s"

    def test_fast_function_completes_with_timeout_set(self):
        """A fast function should complete normally even with a timeout configured."""
        def fast_function(payload):
            return {"status": "success", "outputs": {"result": 42}}

        node = Node(
            node_id="fast_test",
            function_name="fast",
            timeout_seconds=10.0,
            max_retries=0,
        )
        node.function = fast_function

        result = node.execute({})
        assert node.status == NodeStatus.COMPLETED
        assert result["status"] == "success"

    def test_no_timeout_runs_normally(self):
        """Without timeout set, function runs normally."""
        def normal_function(payload):
            return {"status": "success", "outputs": {}}

        node = Node(
            node_id="no_timeout_test",
            function_name="normal",
            timeout_seconds=None,
            max_retries=0,
        )
        node.function = normal_function

        result = node.execute({})
        assert node.status == NodeStatus.COMPLETED


# ======================================================================
# 3D — max_retries semantics
# ======================================================================

class TestMaxRetriesSemantics:
    """Verify that max_retries=N means N retries (1 initial + N retries)."""

    def test_max_retries_3_gives_4_total_attempts(self):
        """max_retries=3 should result in 4 total calls (1 + 3 retries)."""
        call_count = 0

        def always_fail(payload):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        node = Node(
            node_id="retry_test",
            function_name="always_fail",
            max_retries=3,
            retry_delay_seconds=0.01,  # fast for testing
        )
        node.function = always_fail

        result = node.execute({})
        assert call_count == 4, f"Expected 4 total attempts, got {call_count}"
        assert node.status == NodeStatus.FAILED

    def test_max_retries_0_gives_1_attempt(self):
        """max_retries=0 should result in exactly 1 attempt."""
        call_count = 0

        def always_fail(payload):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        node = Node(
            node_id="no_retry_test",
            function_name="always_fail",
            max_retries=0,
            retry_delay_seconds=0.01,
        )
        node.function = always_fail

        result = node.execute({})
        assert call_count == 1
        assert node.status == NodeStatus.FAILED

    def test_retry_succeeds_on_second_attempt(self):
        """If the function succeeds on retry, node should be COMPLETED."""
        call_count = 0

        def fail_then_succeed(payload):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first attempt fails")
            return {"status": "success", "outputs": {"value": 99}}

        node = Node(
            node_id="retry_success_test",
            function_name="fail_then_succeed",
            max_retries=2,
            retry_delay_seconds=0.01,
        )
        node.function = fail_then_succeed

        result = node.execute({})
        assert call_count == 2
        assert node.status == NodeStatus.COMPLETED


# ======================================================================
# 3F — Cancellable retry sleep
# ======================================================================

class TestCancellableRetrySleep:
    """Verify that retry sleep can be cancelled via an abort event."""

    def test_abort_event_cancels_retry_sleep(self):
        """Setting the abort event during retry sleep should raise NodeAbortedError."""
        call_count = 0

        def always_fail(payload):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        abort_event = threading.Event()
        node = Node(
            node_id="abort_test",
            function_name="always_fail",
            max_retries=5,
            retry_delay_seconds=10.0,  # long sleep — should be cancelled
        )
        node.function = always_fail
        node.set_abort_event(abort_event)

        # Set abort after a short delay
        def set_abort():
            time.sleep(0.2)
            abort_event.set()

        t = threading.Thread(target=set_abort)
        t.start()

        start = time.monotonic()
        with pytest.raises(NodeAbortedError):
            node.execute({})
        elapsed = time.monotonic() - start

        t.join()

        # Should have been cancelled quickly (< 2s), not waited 10s
        assert elapsed < 5.0, f"Abort took {elapsed}s — should be quick"
        # Should have run the function once, then been aborted during retry wait
        assert call_count == 1

    def test_no_abort_event_falls_back_to_sleep(self):
        """Without an abort event, retry uses normal sleep."""
        call_count = 0

        def fail_twice(payload):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise RuntimeError("fail")
            return {"status": "success", "outputs": {}}

        node = Node(
            node_id="no_abort_test",
            function_name="fail_twice",
            max_retries=2,
            retry_delay_seconds=0.01,  # fast
        )
        node.function = fail_twice
        # No abort event set

        result = node.execute({})
        assert call_count == 2
        assert node.status == NodeStatus.COMPLETED
