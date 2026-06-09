from __future__ import annotations

import json
import redis
import logging

from functools import lru_cache
from typing import Any, Optional

from hcc_common.config import get_settings


log = logging.getLogger(__name__)

class EventBus:
    def __init__(self) -> None:
        self._cfg = get_settings().bus
        self.r = redis.Redis.from_url(self._cfg.url, decode_responses=True)

    def push(self, queue: str, payload: dict[str, Any]) -> None:
        self.r.rpush(queue, json.dumps(payload, default=str))

    def pop(self, queue: str, timeout: int = 5) -> Optional[dict[str, Any]]:
        item = self.r.blpop([queue], timeout=timeout)
        if not item:
            return None
        _, raw = item
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.error("Dropped malformed queue item: %s", raw[:200])
            return None

    def queue_len(self, queue: str) -> int:
        return int(self.r.llen(queue))

    def push_review(self, payload: dict[str, Any]) -> None:
        self.push(self._cfg.review_queue, payload)

    def pop_review(self, timeout: int = 5) -> Optional[dict[str, Any]]:
        return self.pop(self._cfg.review_queue, timeout)

    def push_train(self, payload: dict[str, Any]) -> None:
        self.push(self._cfg.train_queue, payload)

    def pop_train(self, timeout: int = 5) -> Optional[dict[str, Any]]:
        return self.pop(self._cfg.train_queue, timeout)

    def acquire_cooldown(self, key: str, ttl_seconds: int) -> bool:
        return bool(self.r.set(f"cooldown:{key}", "1", nx=True, ex=ttl_seconds))

    def claim_camera(self, worker_id: str, camera: str, ttl: int = 60) -> bool:
        ok = self.r.set(f"camlease:{camera}", worker_id, nx=True, ex=ttl)
        if ok:
            return True
        return self.r.get(f"camlease:{camera}") == worker_id

    def renew_camera(self, worker_id: str, camera: str, ttl: int = 60) -> None:
        if self.r.get(f"camlease:{camera}") == worker_id:
            self.r.expire(f"camlease:{camera}", ttl)

@lru_cache
def get_bus() -> EventBus:
    return EventBus()