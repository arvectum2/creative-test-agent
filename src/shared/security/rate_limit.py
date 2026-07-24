from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(self):
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, max_attempts: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= max_attempts:
                retry_after = max(1, int(window_seconds - (now - attempts[0])))
                return False, retry_after
            return True, 0

    def record_failure(self, key: str, *, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            attempts.append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()


login_rate_limiter = LoginRateLimiter()
