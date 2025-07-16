import aioredis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis = None

async def get_redis():
    global redis
    if not redis:
        redis = await aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return redis
