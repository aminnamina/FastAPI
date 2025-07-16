import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from redis_cache import get_redis

class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit=5, window=60):
        super().__init__(app)
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next):
        redis = await get_redis()
        client_ip = request.client.host
        key = f"rate:{client_ip}"
        now = int(time.time())
        window_start = now - (now % self.window)
        window_key = f"{key}:{window_start}"
        count = await redis.get(window_key)
        if count is None:
            await redis.set(window_key, 1, ex=self.window)
            count = 1
        else:
            count = int(count) + 1
            await redis.set(window_key, count, ex=self.window)
        if count > self.limit:
            return Response("Too Many Requests", status_code=429)
        return await call_next(request)
