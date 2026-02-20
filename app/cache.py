import hashlib
import json
import logging
from typing import Any, Optional

import redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger("app.cache")


class Cache:
    """Redis cache wrapper."""

    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client = redis.from_url(settings.redis_url, decode_responses=True, encoding="utf-8")
        self.ttl = settings.cache_ttl

    def make_key(self, prefix: str, *args, **kwargs) -> str:
        """Create a cache key from prefix and arguments."""
        key_parts = [prefix]

        # Add positional arguments
        for arg in args:
            key_parts.append(str(arg))

        # Add keyword arguments (sorted for consistency)
        for k, v in sorted(kwargs.items()):
            if v is not None:
                if isinstance(v, (list, dict)):
                    v = json.dumps(v, sort_keys=True)
                key_parts.append(f"{k}:{v}")

        # Create hash for long keys
        key_str = ":".join(key_parts)
        if len(key_str) > 200:
            key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:16]
            return f"{prefix}:{key_hash}"

        return key_str

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        try:
            value = self.redis_client.get(key)
            if value:
                logger.debug(f"Cache hit: {key}")
                return json.loads(value)
            logger.debug(f"Cache miss: {key}")
            return None
        except RedisError as e:
            logger.warning(f"Redis error getting key {key}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode cached value for key {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL."""
        try:
            serialized = json.dumps(value, default=str)
            result = self.redis_client.setex(key, ttl or self.ttl, serialized)
            logger.debug(f"Cache set: {key} (TTL: {ttl or self.ttl}s)")
            return bool(result)
        except (RedisError, TypeError) as e:
            logger.warning(f"Failed to set cache key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            result = bool(self.redis_client.delete(key))
            logger.debug(f"Cache delete: {key}")
            return result
        except RedisError as e:
            logger.warning(f"Failed to delete cache key {key}: {e}")
            return False

    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        try:
            keys = list(self.redis_client.scan_iter(pattern))
            if keys:
                count = self.redis_client.delete(*keys)
                logger.info(f"Cleared {count} cache keys matching pattern: {pattern}")
                return count
            logger.info(f"No cache keys found matching pattern: {pattern}")
            return 0
        except RedisError as e:
            logger.error(f"Failed to clear cache pattern '{pattern}': {e}")
            return 0

    def ping(self) -> bool:
        """Check if Redis is available."""
        try:
            return self.redis_client.ping()
        except RedisError as e:
            logger.debug(f"Redis ping failed: {e}")
            return False


# Global cache instance
cache = Cache()
