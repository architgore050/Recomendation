# VPS Setup Guide

This document explains how to set up the VPS half of the hybrid deployment.

## Prerequisites

1. **VPS instance** — Hetzner CX22 (2 vCPU, 4 GB RAM, 20 GB NVMe) or Oracle A1
   (4 x ARM AMP, 24 GB RAM, $0/mo). This guide assumes 4 GB RAM.
2. **Docker + Compose V2** — `docker compose` (not `docker-compose`).
3. **Cloudflare account** — with `echo-flow.in` domain pointed via Cloudflare
   nameservers.
4. **cloudflared** — installed separately on the VPS for the tunnel.
5. **Tailscale** — installed separately for subnet router.

## Step 1: Cloudflare R2 Bucket Setup

1. In the Cloudflare dashboard, go to **R2** → **Create bucket**.
2. Name: `echoflow-media`
3. Create an **API token** with `Object Read & Write` permissions scoped
    to this bucket.
4. R2 bucket starts fully private by default. Do **not** add a public-read
    policy for `hls/*` — HLS token protection is handled by the Cloudflare
    Worker (see `docs/EXPLAIN/storage/04-hls-token-protection.md`,
    "Option A — Cloudflare Worker").

## Step 2: Cloudflare Tunnel Setup

1. In the Cloudflare dashboard, go to **Tunnels** → **Create tunnel**.
2. Name it `echoflow-vps`.
3. Download the credentials file JSON and save it on the VPS at:
   `/etc/cloudflared/<tunnel-uuid>.json`
4. Create `/etc/cloudflared/config.yml`:

```yaml
tunnel: <tunnel-uuid>
credentials-file: /etc/cloudflared/<tunnel-uuid>.json

ingress:
  - hostname: api.echo-flow.in
    service: http://localhost:80
  - service: http_status:404
```

5. Start the tunnel:

```bash
sudo cloudflared --config /etc/cloudflared/config.yml run
```

6. In the Cloudflare dashboard, add a public hostname `api.echo-flow.in`
   pointing to the tunnel.

## Step 3: Cloudflare Custom Domain for HLS

1. In the **R2** bucket settings, go to **Custom Domains**.
2. Add `media.echo-flow.in` as a custom domain.
3. Cloudflare will provision TLS automatically (Universal SSL).
4. **HLS playback** is now served directly from R2 via
   `https://media.echo-flow.in/hls/{clip_id}/master.m3u8` — no VPS hop.

## Step 4: Deploy on VPS

```bash
# Clone and checkout
git clone https://github.com/your-org/echoflow.git
cd echoflow
git checkout feat/hybrid-vps

# Create .env from template
cp .env.vps.example .env
# EDIT .env with real values:
#   - DJANGO_SECRET_KEY (generate with python -c "...")
#   - DB_PASSWORD
#   - AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (R2 credentials)
#   - AWS_S3_ENDPOINT_URL (your R2 endpoint)
#   - FIELD_ENCRYPTION_KEY (generate with python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# One-shot deploy
bash scripts/vps-deploy.sh
```

The deploy script:
1. Validates pre-flight checks
2. Runs `docker compose -f docker-compose.vps.yml up -d --build`
3. Creates the `vector` extension on the `db` service
4. Runs Django migrations
5. Collects static files
6. Sets up Tailscale subnet router (`--advertise-routes=172.28.0.0/16`)
7. Installs a daily pg_dump backup cron job (uploads to R2)

## Step 5: Tailscale Subnet Router

On the VPS:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --advertise-routes=172.28.0.0/16
```

In the Tailscale admin console, approve the subnet routes for `172.28.0.0/16`.

**Result:** The VPS Docker network (172.28.0.0/16) becomes reachable from
any Tailscale client, including the laptop media worker.

| VPS Container | Fixed IP | Purpose |
|---------------|----------|---------|
| `redis_broker` | 172.28.0.2 | Celery broker |
| `redis_cache` | 172.28.0.3 | Django cache |
| `db` | 172.28.0.4 | PostgreSQL |
| `web` | 172.28.0.10 | Django/gunicorn |
| `celery` | 172.28.0.11 | Default queue |
| `celery_feed` | 172.28.0.12 | Feed queue |
| `celery_beat` | 172.28.0.13 | Scheduler |

## Step 6: Verify

```bash
# API health
curl -I https://api.echo-flow.in/health/

# Media worker heartbeat (should return false until laptop worker starts)
curl https://api.echo-flow.in/api/v1/health/media-worker/

# Django admin (create superuser first)
open https://api.echo-flow.in/admin/
```

## Resource Usage at 50 Users

| Component | Estimated RAM |
|-----------|--------------|
| PostgreSQL + pgvector | ~200 MB |
| Redis broker (512 MB maxmemory) | ~512 MB |
| Redis cache (1 GB maxmemory) | ~1 GB |
| Gunicorn (2 workers × 4 threads) | ~400 MB |
| Celery default worker | ~300 MB |
| Celery feed worker (concurrency=4) | ~300 MB |
| Celery Beat | ~100 MB |
| nginx | ~30 MB |
| **Total** | **~2.9 GB** |

A 4 GB VPS has ~1 GB headroom for Docker overhead, kernel buffers, and
burstable spikes.
