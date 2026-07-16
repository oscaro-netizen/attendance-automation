"""
Duplicate-suppression for inbound Slack events.

Slack redelivers an event (with the same `event_id`) when it does not
receive a timely HTTP 200 from our webhook -- for example, if the app is
briefly overloaded or a deploy is in progress. Without deduplication, a
redelivered event would enqueue a second Celery task for the same
attendance action.

We use Redis `SET key value NX EX <ttl>` as an atomic, distributed
"claim" operation: the first request for a given `event_id` successfully
sets the key and proceeds; any concurrent or subsequent request for the
same `event_id` finds the key already present and is treated as a
duplicate. This is safe across multiple FastAPI worker processes/replicas,
which an in-process cache would not be.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from app.core.config import settings


class SlackEventDeduplicator:
    """Idempotency guard for Slack `event_id` values, backed by Redis."""

    KEY_PREFIX = "slack:event:seen:"

    def __init__(self, redis_client: aioredis.Redis, ttl_seconds: Optional[int] = None):
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds if ttl_seconds is not None else settings.SLACK_EVENT_DEDUPE_TTL_SECONDS

    async def is_duplicate(self, event_id: Optional[str]) -> bool:
        """
        Atomically claims `event_id`. Returns True if the event has already
        been claimed (i.e. it is a duplicate and must NOT be reprocessed),
        or False if this call just claimed it for the first time.

        A falsy `event_id` cannot be deduplicated safely; callers should
        treat that as a validation failure rather than relying on this
        method, which conservatively returns False (not a duplicate) so it
        never silently swallows a legitimate event.
        """
        if not event_id:
            logger.warning("Cannot deduplicate Slack event with empty event_id")
            return False

        key = f"{self.KEY_PREFIX}{event_id}"
        try:
            claimed = await self._redis.set(key, "1", nx=True, ex=self._ttl_seconds)
        except Exception:
            # Fail closed on infrastructure errors would risk dropping
            # legitimate events; fail open and let downstream idempotency
            # (the unique slack_event_id constraint on attendance_logs)
            # act as the last line of defense.
            logger.exception("Redis error while checking Slack event deduplication; failing open")
            return False

        return claimed is None


@lru_cache
def _get_redis_client() -> aioredis.Redis:
    """
    Module-level singleton connection pool, created lazily on first use so
    that importing this module never triggers a network connection.
    """
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_event_deduplicator() -> SlackEventDeduplicator:
    """FastAPI dependency provider for `SlackEventDeduplicator`."""
    return SlackEventDeduplicator(_get_redis_client())
