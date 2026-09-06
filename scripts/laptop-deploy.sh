#!/bin/bash
# =============================================================================
# EchoFlow — Laptop Media Worker Deploy Script
#
# Run this on your laptop to build the media image and start the
# celery_media worker. The worker connects to VPS services via
# Tailscale private network.
#
# Prerequisites:
#   - Docker installed
#   - Tailscale installed and running (connected to the same tailnet as VPS)
#   - VPS already deployed and advertising 172.28.0.0/16 subnet
#   - HF_TOKEN set (in environment or .env)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.laptop.yml"

echo "=== EchoFlow Laptop Deploy ==="

cd "${PROJECT_DIR}"

# ---- Step 0: Pre-flight checks ----
echo "Step 0: Pre-flight checks..."

if [ ! -f ".env" ]; then
    if [ -f ".env.laptop.example" ]; then
        echo "  Copying .env.laptop.example to .env..."
        cp .env.laptop.example .env
        echo "  ✅ EDIT .env WITH YOUR REAL VALUES (DATABASE_URL, REDIS_*, R2 creds, HF_TOKEN)."
    else
        echo "  ERROR: No .env file found. Create one from .env.laptop.example."
        exit 1
    fi
fi

# Check HF_TOKEN (required for media image build)
if [ -z "${HF_TOKEN:-}" ]; then
    if grep -q "^HF_TOKEN=$" .env 2>/dev/null || grep -q "^HF_TOKEN=<" .env 2>/dev/null; then
        echo "  ERROR: HF_TOKEN is not set to a real value in .env."
        echo "  Get a token from https://huggingface.co/settings/tokens"
        exit 1
    fi
fi

if ! command -v docker &>/dev/null; then
    echo "  ERROR: Docker is not installed."
    exit 1
fi

if ! docker compose version &>/dev/null 2>&1; then
    echo "  ERROR: Docker Compose plugin is not installed."
    exit 1
fi

# Check Tailscale connectivity to VPS
echo "  Checking Tailscale connectivity to VPS services..."
DB_HOST=$(grep "^DATABASE_URL=" .env | head -1 | sed -n 's/.*@\([^:]*\):.*/\1/p')
if [ -n "${DB_HOST}" ] && [ "${DB_HOST}" != "<" ]; then
    if ! docker run --rm --network host alpine:latest \
        ping -c 1 -W 3 "${DB_HOST}" >/dev/null 2>&1; then
        echo "  WARNING: Cannot reach ${DB_HOST} via Tailscale."
        echo "  Ensure Tailscale is running and the VPS subnet is approved in the admin console."
    else
        echo "  ✅ Can reach VPS database at ${DB_HOST}"
    fi
else
    echo "  WARNING: Could not parse DATABASE_URL for connectivity check."
fi

echo "  ✅ Docker and required tools are available."

# ---- Step 1: Build media image ----
echo "Step 1: Building media image (this bakes in Whisper + SentenceTransformer + KeyBERT)..."
# If you change any model version, rebuild the media image with --no-cache.
docker build --target media -t echoflow-media:local --secret id=hf_token,env=HF_TOKEN .

# ---- Step 2: Start the media worker ----
echo "Step 2: Starting celery_media worker..."
docker compose -f "${COMPOSE_FILE}" up -d

# ---- Step 3: Start heartbeat (background process) ----
echo "Step 3: Starting heartbeat script..."
# The heartbeat writes media_worker:alive to Redis every 30s (60s TTL).
# Run it as a background process.
if command -v nohup &>/dev/null; then
    REDIS_BROKER_URL=$(grep "^REDIS_BROKER_URL=" .env | cut -d= -f2-)
    REDIS_BROKER_URL="${REDIS_BROKER_URL}" nohup bash "${PROJECT_DIR}/scripts/laptop-heartbeat.sh" > /tmp/echoflow-heartbeat.log 2>&1 &
    echo "  ✅ Heartbeat started (PID: $!)"
    echo "  Logs: /tmp/echoflow-heartbeat.log"
else
    echo "  WARNING: nohup not available. Run this manually:"
    echo "    nohup bash ${PROJECT_DIR}/scripts/laptop-heartbeat.sh > /tmp/echoflow-heartbeat.log 2>&1 &"
fi

# ---- Step 4: Show logs ----
echo ""
echo "=== Laptop Deploy Complete ==="
echo ""
echo "Worker logs (Ctrl+C to detach):"
docker compose -f "${COMPOSE_FILE}" logs -f celery_media
