"""Tests for the media worker heartbeat endpoint."""
import pytest
from rest_framework.test import APIRequestFactory
from backend.app.views.system_health import media_worker_health


pytestmark = pytest.mark.django_db


class TestMediaWorkerHealth:
    def test_returns_true_when_heartbeat_key_exists(self, settings, monkeypatch):
        """When the heartbeat key exists, return 200 with media_worker_alive=true."""
        mock_redis = type('MockRedis', (), {
            'get': lambda self, key: b'1700000000',
            'close': lambda self: None,
        })()
        monkeypatch.setattr('redis.Redis.from_url', lambda url: mock_redis)

        factory = APIRequestFactory()
        request = factory.get('/api/v1/health/media-worker/')
        response = media_worker_health(request)

        assert response.status_code == 200
        assert response.data == {"media_worker_alive": True}

    def test_returns_false_when_heartbeat_key_missing(self, settings, monkeypatch):
        """When the heartbeat key is missing, return 200 with media_worker_alive=false."""
        mock_redis = type('MockRedis', (), {
            'get': lambda self, key: None,
            'close': lambda self: None,
        })()
        monkeypatch.setattr('redis.Redis.from_url', lambda url: mock_redis)

        factory = APIRequestFactory()
        request = factory.get('/api/v1/health/media-worker/')
        response = media_worker_health(request)

        assert response.status_code == 200
        assert response.data == {"media_worker_alive": False}

    def test_returns_503_when_redis_unreachable(self, settings, monkeypatch):
        """When Redis is unreachable, return 503 with media_worker_alive=false."""
        from redis.exceptions import RedisError

        def mock_from_url(url):
            raise RedisError("connection refused")

        monkeypatch.setattr('redis.Redis.from_url', mock_from_url)

        factory = APIRequestFactory()
        request = factory.get('/api/v1/health/media-worker/')
        response = media_worker_health(request)

        assert response.status_code == 503
        assert response.data == {"media_worker_alive": False}

    def test_uses_broker_redis_url(self, settings, monkeypatch):
        """The endpoint must read from REDIS_BROKER_URL, not REDIS_CACHE_URL."""
        captured_urls = []

        class MockRedis:
            def get(self, key):
                return None

            def close(self):
                pass

        def mock_from_url(url):
            captured_urls.append(url)
            return MockRedis()

        monkeypatch.setattr('redis.Redis.from_url', mock_from_url)
        monkeypatch.setattr(settings, 'REDIS_BROKER_URL', 'redis://test-broker:6379/0')
        monkeypatch.setattr(settings, 'REDIS_CACHE_URL', 'redis://test-cache:6379/0')

        factory = APIRequestFactory()
        request = factory.get('/api/v1/health/media-worker/')
        media_worker_health(request)

        assert captured_urls == ['redis://test-broker:6379/0']
