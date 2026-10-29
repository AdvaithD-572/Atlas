import hashlib
import hmac
import threading
import time
from collections import deque
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from atlas.errors import AtlasError

bearer = HTTPBearer(auto_error=False)


class RateLimiter:
    """Bounded, process-local admission control; not a distributed rate limit."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._entries: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def admit(self, owner: str) -> None:
        now = time.monotonic()
        with self._lock:
            entries = self._entries.setdefault(owner, deque())
            while entries and entries[0] <= now - 60:
                entries.popleft()
            if len(entries) >= self.limit:
                raise AtlasError("rate_limited", "Request limit reached. Retry in one minute.", 429)
            entries.append(now)


def principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None or len(credentials.credentials) > 512:
        raise AtlasError("unauthorized", "A valid bearer token is required.", 401)
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    matched: str | None = None
    for owner, expected in request.app.state.settings.token_hashes.items():
        if hmac.compare_digest(digest, expected):
            matched = owner
    if matched is None:
        raise AtlasError("unauthorized", "A valid bearer token is required.", 401)
    request.app.state.limiter.admit(matched)
    return matched
