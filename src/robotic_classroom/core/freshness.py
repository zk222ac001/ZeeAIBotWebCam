"""Freshness is measured from producer time, never consumer polling time."""
import math
import time


def is_fresh(timestamp: float, timeout_ms: int, now: float | None = None) -> bool:
    age = (time.monotonic() if now is None else now) - timestamp
    return math.isfinite(age) and 0 <= age <= timeout_ms / 1000.0
