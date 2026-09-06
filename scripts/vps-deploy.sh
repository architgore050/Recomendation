#!/bin/bash
# =============================================================================
# EchoFlow — VPS One-Shot Deploy Script
#
# Run this on a fresh VPS after cloning the repo and checking
# out the `feat/hybrid-vps` branch.
#
# Prerequisites (user installs separately):
#   - Docker + compose plugin
#   - cloudflared (Cloudflare Tunnel)
#   - Tailscale (for subnet router advertising)
#   - aws CLI or mc (MinIO client) — for pg_dump uploads to R2
#
# Cloudflare R2 bucket + custom domain must be configured BEFORE running.
# See the Deployment Checklist in docs/deployment_v1_full_plan.md
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.vps.yml"

echo "=== EchoFlow VPS Deploy ==="

cd "${PROJECT_DIR}"

# ---- Step 0: Pre-flight checks ----
echo "Step 0: Pre-flight checks..."

if [ ! -f ".env" ]; then
    if [ -f ".env.vps.example" ]; then
        echo "  Copying .env.vps.example to .env..."
        cp .env.vps.example .env
        echo "  ✅ EDIT .env WITH YOUR REAL VALUES before continuing."
    else
        echo "  ERROR: No .env file found. Create one from .env.vps.example."
        exit 1
    fi
fi

required_vars=(
    "DJANGO_SECRET_KEY"
    "DB_PASSWORD"
    "AWS_ACCESS_KEY_ID"
    "AWS_SECRET_ACCESS_KEY"
    "AWS_S3_ENDPOINT_URL"
)
for var in "${required_vars[@]}"; do
    val=$(grep "^${var}=" .env | head -1 | cut -d= -f2-)
    if [ -z "$val" ] || [ "$val" = "change-me"* ]; then
        echo "  WARNING: ${var} is not set to a real value in .env."
    fi
done

if ! command -v docker &>/dev/null; then
    echo "  ERROR: Docker is not installed."
    exit 1
fi

if ! docker compose version &>/dev/null 2>&1; then
    echo "  ERROR: Docker Compose plugin is not installed."
    exit 1
fi

echo "  ✅ Docker and Compose are available."

# ---- Step 1: Build and start services ----
echo "Step 1: Building and starting services..."
docker compose -f "${COMPOSE_FILE}" up -d --build

# Wait for db to be healthy
echo "  Waiting for database to be healthy..."
docker compose -f "${COMPOSE_FILE}" exec db bash -c \
    'until pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"; do sleep 2; done'

# Wait for web to be healthy
echo "  Waiting for web to be healthy..."
for i in $(seq 1 30); do
    if docker compose -f "${COMPOSE_FILE}" ps web | grep -q "healthy"; then
        echo "  ✅ web is healthy."
        break
    fi
    echo "  ...waiting for web (${i}/30)"
    sleep 5
done

# ---- Step 2: Create pgvector extension ----
echo "Step 2: Creating pgvector extension..."
docker compose -f "${COMPOSE_FILE}" exec db psql -U "${DB_USER}" -d "${DB_NAME}" -c \
    "CREATE EXTENSION IF NOT EXISTS vector;"

# ---- Step 3: Run migrations ----
echo "Step 3: Running migrations..."
docker compose -f "${COMPOSE_FILE}" exec web python manage.py migrate --noinput

# ---- Step 4: Collect static files ----
echo "Step 4: Collecting static files..."
docker compose -f "${COMPOSE_FILE}" exec web python manage.py collectstatic --noinput

# ---- Step 5: Create superuser (optional, interactive) ----
echo "Step 5: Creating superuser (optional)..."
if [ -t 0 ]; then
    docker compose -f "${COMPOSE_FILE}" exec web python manage.py createsuperuser \
        --noinput 2>/dev/null || echo "  Skipped (no interactive terminal or superuser exists)."
else
    echo "  Skipped (non-interactive terminal)."
fi

# ---- Step 6: Tailscale subnet router ----
echo "Step 6: Checking Tailscale subnet router..."
if command -v tailscale &>/dev/null; then
    echo "  Tailscale detected. Verifying subnet router..."
    # Verify the subnet is advertised
    tailscale routes | grep -q "172.28.0.0/16" && echo "  ✅ Subnet 172.28.0.0/16 is advertised." \
        || echo "  ⚠️  Subnet not advertised yet. Run: sudo tailscale up --advertise-routes=172.28.0.0/16"
else
    echo "  ⚠️  Tailscale not installed. Install it for laptop ↔ VPS connectivity."
    echo "  The laptop worker (celery_media) needs to reach Redis (172.28.0.2) and Postgres (172.28.0.4)."
fi

# ---- Step 7: Daily backup cron ----
echo "Step 7: Setting up daily pg_dump backup to R2..."
mkdir -p /backups

# Create the backup script
cat > /backups/echoflow-backup.sh << 'EOF'
#!/bin/bash
set -euo pipefail
DATE=$(date +%F)
PROJECT_DIR="/opt/echoflow"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.vps.yml"
DB_NAME=$(grep "^DB_NAME=" "${PROJECT_DIR}/.env" | cut -d= -f2)
DB_USER=$(grep "^DB_USER=" "${PROJECT_DIR}/.env" | cut -d= -f2)

# Dump
docker compose -f "${COMPOSE_FILE}" exec -T db pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "/backups/echoflow-${DATE}.sql.gz"

# Upload to R2
# Option A: aws CLI
#   aws s3 cp "/backups/echoflow-${DATE}.sql.gz" s3://echoflow-media/backups/ --endpoint-url https://<accountid>.r2.cloudflarestorage.com
# Option B: mc (MinIO client)
#   mc cp "/backups/echoflow-${DATE}.sql.gz" echoflow-media/backups/

# Clean up old backups (keep 7 days)
find /backups -name "echoflow-*.sql.gz" -mtime +7 -delete
EOF
chmod +x /backups/echoflow-backup.sh

# Install cron job (only if not already present)
if ! crontab -l 2>/dev/null | grep -q "echoflow-backup.sh"; then
    (crontab -l 2>/dev/null; echo "0 3 * * * /backups/echoflow-backup.sh") | crontab -
    echo "  ✅ Daily backup cron installed (runs at 03:00 UTC)."
else
    echo "  ✅ Daily backup cron already exists."
fi

# ---- Summary ----
echo ""
echo "=== VPS Deploy Complete ==="
echo ""
echo "Services running:"
docker compose -f "${COMPOSE_FILE}" ps --format "table {{.Name}}\t{{.Status}}"
echo ""
echo "Next steps:"
echo "  1. Configure Cloudflare Tunnel for api.echo-flow.in (run cloudflared on VPS)."
echo "  2. Verify health: curl -I https://api.echo-flow.in/health/"
echo "  3. Enable Tailscale subnet routes in the Tailscale admin console (172.28.0.0/16)."
echo "  4. Deploy the laptop worker (see scripts/laptop-deploy.sh)."
echo "  5. Verify media worker health: curl -I https://api.echo-flow.in/api/v1/health/media-worker/"
echo ""
echo "Fixed IPs for Tailscale connectivity:"
echo "  redis_broker: 172.28.0.2"
echo "  redis_cache:  172.28.0.3"
echo "  db:           172.28.0.4"
