import asyncio
import json
import time
from typing import Any


class RateLimiter:
    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._next_slot: dict[str, float] = {}

    async def wait(self, key: str) -> None:
        """Reserves the next free slot for the key, then sleeps until it is reached."""
        now = time.monotonic()
        slot = max(now, self._next_slot.get(key, now))
        self._next_slot[key] = slot + self.interval
        await asyncio.sleep(slot - now)


class TtlCache:
    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._items: dict[str, tuple[float, Any]] = {}

    @staticmethod
    def key(tool: str, args: dict[str, Any]) -> str:
        return tool + json.dumps(args, sort_keys=True)

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.monotonic():
            del self._items[key]
            return None
        return value

    def put(self, key: str, value: Any) -> None:
        self._items[key] = (time.monotonic() + self.ttl, value)
