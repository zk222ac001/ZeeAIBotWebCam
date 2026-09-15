from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


@dataclass(slots=True)
class ControlLease:
    token: str
    owner: str
    expires_at: float

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self.expires_at


class ControlLeaseManager:
    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self._lease: ControlLease | None = None

    def acquire(self, owner: str) -> ControlLease:
        now = time.monotonic()
        if self._lease is not None and not self._lease.expired:
            raise RuntimeError("control lease already held")
        self._lease = ControlLease(
            token=secrets.token_urlsafe(24),
            owner=owner,
            expires_at=now + self.ttl_seconds,
        )
        return self._lease

    def validate(self, token: str | None) -> bool:
        return (
            self._lease is not None
            and not self._lease.expired
            and token is not None
            and secrets.compare_digest(token, self._lease.token)
        )

    def renew(self, token: str | None) -> bool:
        """Extend an active lease after authenticating its token."""
        if not self.validate(token):
            return False
        assert self._lease is not None
        self._lease.expires_at = time.monotonic() + self.ttl_seconds
        return True

    def release(self, token: str) -> None:
        if self.validate(token):
            self._lease = None

    def clear(self) -> None:
        self._lease = None
