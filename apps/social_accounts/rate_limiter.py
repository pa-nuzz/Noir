import time
from collections import defaultdict
from datetime import datetime, timedelta


class PlatformRateLimiter:
    def __init__(self):
        self._windows = defaultdict(list)

    def _clean(self, key):
        now = time.time()
        self._windows[key] = [t for t in self._windows[key] if now - t < 60]

    def check(self, platform, max_requests=30, window=60):
        key = f"{platform}"
        self._clean(key)
        return len(self._windows[key]) < max_requests

    def consume(self, platform):
        key = f"{platform}"
        self._windows[key].append(time.time())

    def wait_time(self, platform, max_requests=30, window=60):
        key = f"{platform}"
        self._clean(key)
        if len(self._windows[key]) < max_requests:
            return 0
        oldest = min(self._windows[key])
        return max(0, 60 - (time.time() - oldest))


rate_limiter = PlatformRateLimiter()
