"""The Redis-backed idempotency guard in front of the Celery queue."""
import pytest

from app.slack.event_deduplicator import SlackEventDeduplicator

pytestmark = pytest.mark.asyncio


class FakeRedis:
    """Implements just enough of `SET key value NX EX ttl`."""

    def __init__(self, fail: bool = False):
        self.store = {}
        self.fail = fail
        self.ttls = {}

    async def set(self, key, value, nx=False, ex=None):
        if self.fail:
            raise ConnectionError("redis is down")
        if nx and key in self.store:
            return None
        self.store[key] = value
        self.ttls[key] = ex
        return True


async def test_the_first_sighting_of_an_event_is_not_a_duplicate():
    dedupe = SlackEventDeduplicator(FakeRedis())
    assert await dedupe.is_duplicate("Ev_1") is False


async def test_a_second_sighting_is_a_duplicate():
    dedupe = SlackEventDeduplicator(FakeRedis())
    await dedupe.is_duplicate("Ev_1")
    assert await dedupe.is_duplicate("Ev_1") is True


async def test_distinct_events_do_not_collide():
    dedupe = SlackEventDeduplicator(FakeRedis())
    assert await dedupe.is_duplicate("Ev_1") is False
    assert await dedupe.is_duplicate("Ev_2") is False


async def test_the_claim_expires_so_redis_does_not_grow_without_bound():
    redis = FakeRedis()
    dedupe = SlackEventDeduplicator(redis, ttl_seconds=42)
    await dedupe.is_duplicate("Ev_1")
    assert set(redis.ttls.values()) == {42}


async def test_an_empty_event_id_is_never_treated_as_a_duplicate():
    dedupe = SlackEventDeduplicator(FakeRedis())
    assert await dedupe.is_duplicate(None) is False
    assert await dedupe.is_duplicate("") is False


async def test_a_redis_outage_fails_open():
    """
    Dropping legitimate events would be worse than the rare double-process that
    the database's unique `slack_event_id` constraint still catches downstream.
    """
    dedupe = SlackEventDeduplicator(FakeRedis(fail=True))
    assert await dedupe.is_duplicate("Ev_1") is False
