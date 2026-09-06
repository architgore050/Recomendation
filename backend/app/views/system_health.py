"""Heartbeat endpoint: reports whether the laptop media worker is alive.

The laptop worker writes `media_worker:alive` to the broker Redis every
30 seconds (see scripts/laptop-heartbeat.sh). This endpoint reads that
key and returns a boolean. The frontend uses it to show a
"Processing delayed" badge when no media worker is reachable.
"""
from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
import logging

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def media_worker_health(request):
    """Check if the media worker (laptop) is alive.

    Reads the `media_worker:alive` key from the broker Redis.
    The laptop writes this key every 30 seconds with a 60-second TTL.
    If the key is absent (worker offline, laptop asleep, or heartbeat
    script stopped), the worker is considered offline.

    Returns:
        200: {"media_worker_alive": true/false}
        503: {"media_worker_alive": false} (Redis unreachable — treated
             as "not alive" so the frontend shows "Processing delayed")
    """
    try:
        client = Redis.from_url(settings.REDIS_BROKER_URL)
        value = client.get("media_worker:alive")
        if value is not None:
            client.close()
            return Response({"media_worker_alive": True})
        client.close()
        return Response({"media_worker_alive": False})
    except RedisError:
        logger.warning("Redis unreachable when checking media worker heartbeat")
        return Response({"media_worker_alive": False}, status=503)
