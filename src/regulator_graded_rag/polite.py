# Author: Nicola Antonello
"""Requests spaced in time and retried with waits, for servers that throttle clients.

The Internet Archive publishes no rate limit. The EDGI wayback library's v0.5.1 notes
(2026-06-19) cut its default to 24 searches a minute to match the hard limits the
archive's servers now set. A Paced getter starts each request at least `interval`
seconds after the previous one started, and after a 429, a 5xx or a network error it
waits 10, 60 and then 300 seconds before trying again, and then gives up.
"""

import time
from collections.abc import Callable, Sequence
from http.client import HTTPException

from regulator_graded_rag.fetch import RETRY_STATUSES, FetchError, Get, Response

WAITS = (10.0, 60.0, 300.0)


class Paced:
    """A Get that spaces its requests, and retries the throttled or failed ones."""

    def __init__(
        self,
        get: Get,
        *,
        interval: float,
        waits: Sequence[float] = WAITS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._get = get
        self._interval = interval
        self._waits = tuple(waits)
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None  # when the previous request started

    def __call__(self, url: str) -> Response:
        """The first answer whose status is not in RETRY_STATUSES, whatever it is."""
        last = ""
        for wait in (0.0, *self._waits):
            if wait:
                self._sleep(wait)
            self._space()
            try:
                response = self._get(url)
            except (OSError, HTTPException) as err:
                last = f"{type(err).__name__}: {err}"
                continue
            if response.status not in RETRY_STATUSES:
                return response
            last = f"HTTP {response.status}"
        raise FetchError(f"{url}: failed after {len(self._waits) + 1} attempts: {last}")

    def _space(self) -> None:
        """Sleep whatever is left of the interval since the previous request started."""
        if self._last is not None:
            left = self._interval - (self._clock() - self._last)
            if left > 0:
                self._sleep(left)
        self._last = self._clock()
