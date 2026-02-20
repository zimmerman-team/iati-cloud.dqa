import json
from unittest.mock import Mock, patch

import pytest  # noqa: F401
from redis.exceptions import RedisError

from app.cache import Cache


class TestCache:
    """Tests for Cache class."""

    def test_make_key_simple(self):
        """Test simple key generation."""
        cache = Cache()
        key = cache.make_key("prefix", "arg1", "arg2")
        assert key == "prefix:arg1:arg2"

    def test_make_key_with_kwargs(self):
        """Test key generation with keyword arguments."""
        cache = Cache()
        key = cache.make_key("prefix", org="GB-GOV-1", country="AF")
        assert "prefix" in key
        assert "org:GB-GOV-1" in key or "country:AF" in key

    def test_make_key_with_dict(self):
        """Test key generation with dictionary values."""
        cache = Cache()
        key = cache.make_key("prefix", filters={"country": "AF", "sector": "151"})
        assert "prefix" in key

    def test_make_key_long_hashing(self):
        """Test that long keys are hashed."""
        cache = Cache()
        long_string = "x" * 250
        key = cache.make_key("prefix", long_string)
        # Hash should make it shorter
        assert len(key) < 50

    @patch("app.cache.redis")
    def test_get_success(self, mock_redis_module):
        """Test successful cache get."""
        mock_client = Mock()
        mock_client.get.return_value = json.dumps({"test": "data"})
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.get("test_key")

        assert result == {"test": "data"}
        mock_client.get.assert_called_once_with("test_key")

    @patch("app.cache.redis")
    def test_get_not_found(self, mock_redis_module):
        """Test cache get when key not found."""
        mock_client = Mock()
        mock_client.get.return_value = None
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.get("nonexistent_key")

        assert result is None

    @patch("app.cache.redis")
    def test_get_redis_error(self, mock_redis_module):
        """Test get handles RedisError."""
        mock_client = Mock()
        mock_client.get.side_effect = RedisError()
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.get("test_key")
        assert result is None

    @patch("app.cache.redis")
    def test_get_json_decode_error(self, mock_redis_module):
        """Test get handles JSONDecodeError."""
        mock_client = Mock()
        # Return invalid JSON
        mock_client.get.return_value = "{invalid_json:}"
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.get("test_key")
        assert result is None

    @patch("app.cache.redis")
    def test_set_success(self, mock_redis_module):
        """Test successful cache set."""
        mock_client = Mock()
        mock_client.setex.return_value = True
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        cache.ttl = 3600
        result = cache.set("test_key", {"test": "data"})

        assert result is True
        mock_client.setex.assert_called_once()

    @patch("app.cache.redis")
    def test_set_with_custom_ttl(self, mock_redis_module):
        """Test cache set with custom TTL."""
        mock_client = Mock()
        mock_client.setex.return_value = True
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.set("test_key", {"test": "data"}, ttl=1800)

        assert result is True
        args = mock_client.setex.call_args
        assert args[0][1] == 1800  # TTL should be 1800

    @patch("app.cache.redis")
    def test_set_redis_error(self, mock_redis_module):
        """Test set handles RedisError."""
        mock_client = Mock()
        mock_client.setex.side_effect = RedisError()
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.set("test_key", {"test": "data"})
        assert result is False

    @patch("app.cache.redis")
    def test_set_type_error(self, mock_redis_module):
        """Test set handles TypeError."""
        mock_client = Mock()
        # TypeError will be raised by json.dumps, so patch it
        with patch("json.dumps", side_effect=TypeError()):
            mock_redis_module.from_url.return_value = mock_client
            cache = Cache()
            result = cache.set("test_key", object())
            assert result is False

    @patch("app.cache.redis")
    def test_delete_success(self, mock_redis_module):
        """Test successful cache delete."""
        mock_client = Mock()
        mock_client.delete.return_value = 1
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.delete("test_key")

        assert result is True
        mock_client.delete.assert_called_once_with("test_key")

    @patch("app.cache.redis")
    def test_delete_redis_error(self, mock_redis_module):
        """Test delete handles RedisError."""
        mock_client = Mock()
        mock_client.delete.side_effect = RedisError()
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.delete("test_key")
        assert result is False

    @patch("app.cache.redis")
    def test_clear_pattern(self, mock_redis_module):
        """Test clearing keys by pattern."""
        mock_client = Mock()
        mock_client.scan_iter.return_value = iter(["key1", "key2", "key3"])
        mock_client.delete.return_value = 3
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.clear_pattern("test:*")

        assert result == 3
        mock_client.scan_iter.assert_called_once_with("test:*")
        mock_client.delete.assert_called_once_with("key1", "key2", "key3")

    @patch("app.cache.redis")
    def test_clear_pattern_redis_error(self, mock_redis_module):
        """Test clear_pattern handles RedisError."""
        mock_client = Mock()
        mock_client.scan_iter.side_effect = RedisError()
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.clear_pattern("test:*")
        assert result == 0

    @patch("app.cache.redis")
    def test_clear_pattern_no_keys(self, mock_redis_module):
        """Test clear_pattern returns 0 when no keys found."""
        mock_client = Mock()
        mock_client.scan_iter.return_value = iter([])
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.clear_pattern("test:*")
        assert result == 0
        mock_client.scan_iter.assert_called_once_with("test:*")

    @patch("app.cache.redis")
    def test_ping_success(self, mock_redis_module):
        """Test successful Redis ping."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.ping()

        assert result is True
        mock_client.ping.assert_called_once()

    @patch("app.cache.redis")
    def test_ping_failure(self, mock_redis_module):
        """Test Redis ping failure."""
        mock_client = Mock()
        mock_client.ping.side_effect = RedisError()
        mock_redis_module.from_url.return_value = mock_client

        cache = Cache()
        result = cache.ping()

        assert result is False
        mock_client.ping.assert_called_once()
