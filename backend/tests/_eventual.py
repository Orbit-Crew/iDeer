"""Shared event-style wait helpers for tests that observe cross-thread work.

Code review 09-M1 flagged 40+ test files that used fixed ``time.sleep`` to
wait for another thread / event loop to produce an observable effect — the
classic flake pattern (slow CI machine: asserted-too-early; fast machine:
white wait). Replace those sleeps with :func:`wait_until` (sync) or
:func:`await wait_until_async` (async): both poll a predicate until it holds
or a total deadline expires, then fail with the last observed state instead
of silently proceeding.

For handshakes where the producer can cooperate directly, prefer a
``threading.Event`` / ``asyncio.Future`` set by the producer — a predicate
poll is the fallback for code you cannot instrument.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_INTERVAL_SECONDS = 0.01


def wait_until(
    predicate: Callable[[], object],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    message: str | None = None,
) -> object:
    """Poll ``predicate`` until its result is truthy or ``timeout`` expires.

    Returns the truthy result. Raises ``AssertionError`` (with the last
    falsy result) instead of silently proceeding on timeout, so a slow
    machine surfaces as a named failure rather than a confusing downstream
    assert.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = predicate()
        if result:
            return result
        if time.monotonic() >= deadline:
            detail = message or f"condition not met within {timeout}s"
            raise AssertionError(f"{detail}; last observed result: {result!r}")
        time.sleep(interval)


async def wait_until_async(
    predicate: Callable[[], object],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    message: str | None = None,
) -> object:
    """Async twin of :func:`wait_until` — yields the loop between polls."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        result = predicate()
        if result:
            return result
        if loop.time() >= deadline:
            detail = message or f"condition not met within {timeout}s"
            raise AssertionError(f"{detail}; last observed result: {result!r}")
        await asyncio.sleep(interval)


def wait_for_event(event: threading.Event, *, timeout: float = DEFAULT_TIMEOUT_SECONDS, message: str | None = None) -> None:
    """Wait for a producer-set ``threading.Event``; assert (don't proceed silently) on timeout."""
    if not event.wait(timeout):
        raise AssertionError(message or f"event not set within {timeout}s")
