from __future__ import annotations

import time


class DeadmanTimer:
    def __init__(self, timeout_ms: int) -> None:
        self.timeout_seconds = timeout_ms / 1000.0
        self._last_heartbeat: float | None = None

    def heartbeat(self) -> None:
        self._last_heartbeat = time.monotonic()

    def clear(self) -> None:
        self._last_heartbeat = None

    @property
    def fresh(self) -> bool:
        return (
            self._last_heartbeat is not None
            and (time.monotonic() - self._last_heartbeat) <= self.timeout_seconds
        )
