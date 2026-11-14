# Author: Nicola Antonello
from collections.abc import Callable

import pytest

from regulator_graded_rag.fetch import FetchError, Response
from regulator_graded_rag.polite import Paced


class Clock:
    """A clock that only moves when something sleeps on it."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def answers(*statuses: int) -> Callable[[str], Response]:
    it = iter(statuses)
    return lambda url: Response(next(it), "text/html", b"")


def test_requests_are_spaced_by_the_interval() -> None:
    clock = Clock()
    paced = Paced(answers(200, 200), interval=3.0, sleep=clock.sleep, clock=clock.now)
    paced("a")
    clock.t += 1.0
    paced("b")
    assert clock.slept == [2.0]


def test_throttled_requests_wait_and_retry() -> None:
    clock = Clock()
    paced = Paced(
        answers(429, 503, 200), interval=3.0, sleep=clock.sleep, clock=clock.now
    )
    assert paced("a").status == 200
    assert clock.slept == [10.0, 60.0]


def test_a_request_that_keeps_failing_raises() -> None:
    clock = Clock()

    def down(url: str) -> Response:
        raise OSError("connection reset")

    with pytest.raises(FetchError, match="after 4 attempts"):
        Paced(down, interval=0.0, sleep=clock.sleep, clock=clock.now)("a")
    assert clock.slept == [10.0, 60.0, 300.0]


def test_other_statuses_come_back_at_once() -> None:
    clock = Clock()
    paced = Paced(answers(404), interval=3.0, sleep=clock.sleep, clock=clock.now)
    assert paced("a").status == 404
    assert clock.slept == []
