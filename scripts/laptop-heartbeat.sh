#!/bin/bash
# =============================================================================
# EchoFlow — Laptop Heartbeat Script
#
# Writes the `media_worker:alive` key to the broker Redis every 30 seconds.
# The key has a 60-second TTL, so if this script stops (worker crash,
# laptop sleep, Tailscale disconnect), the key expires and the API
# endpoint correctly reports the worker as offline.
#
# Usage:
#   nohup bash scripts/laptop-heartbeat.sh > /tmp/heartbeat.log 2>&1 &
#
# To stop: kill the process or pkill -f "laptop-heartbeat.sh"
# =============================================================================

set -euo pipefail

# Use the Redis broker URL from .env (via Tailscale to VPS)
REDIS_URL="${REDIS_BROKER_URL:-redis://172.28.0.2:6379/0}"

echo "Starting EchoFlow heartbeat..."
echo "  Redis: ${REDIS_URL}"
echo "  Interval: 30s"
echo "  TTL: 60s"
echo ""

# Ensure redis-cli is available (fallback to a python one-liner if not)
if command -v redis-cli &>/dev/null; then
    while true; do
        redis-cli -u "${REDIS_URL}" SET media_worker:alive "$(date +%s)" EX 60
        echo "  [$(date '+%Y-%m-%d %H:%M:%S')] Heartbeat OK"
        sleep 30
    done
else
    echo "  redis-cli not found — falling back to python redis client"
    while true; do
        python -c "
import redis, sys
try:
    r = redis.from_url('${REDIS_URL}')
    r.set('media_worker:alive', __import__('time').time(), ex=60)
    r.close()
    print(f'  [{__import__(\"datetime\").datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")}] Heartbeat OK')
except Exception as e:
    print(f'  [{__import__(\"datetime\").datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")}] Heartbeat FAILED: {e}', file=sys.stderr)
" 2>&1
        sleep 30
    done
fi
