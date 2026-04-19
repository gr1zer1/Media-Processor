import sys
import types


class FakeRedisClient:
    def __init__(self):
        self.storage = {}
        self.last_set = None

    def __await__(self):
        async def _return_self():
            return self

        return _return_self().__await__()

    async def get(self, key):
        return self.storage.get(key)

    async def set(self, key, value, ex=None):
        self.storage[key] = value
        self.last_set = {"key": key, "value": value, "ex": ex}


def _install_redis_stub():
    if "redis.asyncio" in sys.modules:
        return

    redis_module = types.ModuleType("redis")
    redis_asyncio_module = types.ModuleType("redis.asyncio")

    def from_url(_url):
        return FakeRedisClient()

    redis_asyncio_module.Redis = FakeRedisClient
    redis_asyncio_module.from_url = from_url
    redis_module.asyncio = redis_asyncio_module

    sys.modules["redis"] = redis_module
    sys.modules["redis.asyncio"] = redis_asyncio_module


def _install_fastapi_limiter_stub():
    if "fastapi_limiter.depends" in sys.modules:
        return

    fastapi_limiter_module = types.ModuleType("fastapi_limiter")
    depends_module = types.ModuleType("fastapi_limiter.depends")

    class FastAPILimiter:
        @staticmethod
        async def init(_redis):
            return None

    class RateLimiter:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __call__(self):
            return None

    fastapi_limiter_module.FastAPILimiter = FastAPILimiter
    depends_module.RateLimiter = RateLimiter

    sys.modules["fastapi_limiter"] = fastapi_limiter_module
    sys.modules["fastapi_limiter.depends"] = depends_module


_install_redis_stub()
_install_fastapi_limiter_stub()
