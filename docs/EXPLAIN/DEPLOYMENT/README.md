# Deployment Documentation

This directory contains documentation for deploying EchoFlow in various
configurations.

## Deployments

- [01-hybrid-deployment-overview.md](01-hybrid-deployment-overview.md) — Architecture of the hybrid VPS + laptop + Cloudflare R2 deployment
- [02-vps-setup.md](02-vps-setup.md) — Step-by-step guide for VPS deployment (Hetzner/Oracle + Cloudflare Tunnel + Tailscale)
- [03-laptop-media-worker.md](03-laptop-media-worker.md) — Step-by-step guide for laptop media worker setup
- [04-cloudflare-config.md](04-cloudflare-config.md) — R2 bucket policy, Tunnel, Pages, and DNS configuration
- [05-data-flow.md](05-data-flow.md) — End-to-end data flow in the hybrid deployment

## Quick Start

```bash
# 1. Deploy VPS
git checkout feat/hybrid-vps
cp .env.vps.example .env
# Edit .env with real values
bash scripts/vps-deploy.sh

# 2. Deploy laptop worker
git checkout feat/hybrid-laptop
cp .env.laptop.example .env
# Edit .env with real values (DJANGO_SECRET_KEY must match VPS)
bash scripts/laptop-deploy.sh
```

## Deployment Files

| File | Branch | Purpose |
|------|--------|---------|
| `docker-compose.vps.yml` | `feat/hybrid-vps` | VPS production compose (8 services) |
| `docker-compose.laptop.yml` | `feat/hybrid-laptop` | Laptop media worker compose (1 service) |
| `.env.vps.example` | `feat/hybrid-vps` | VPS environment template |
| `.env.laptop.example` | `feat/hybrid-laptop` | Laptop environment template |
| `scripts/vps-deploy.sh` | `feat/hybrid-vps` | One-shot VPS deploy |
| `scripts/laptop-deploy.sh` | `feat/hybrid-laptop` | One-shot laptop deploy |
| `scripts/laptop-heartbeat.sh` | `feat/hybrid-laptop` | Background heartbeat script |

## Related Docs

- `docs/EXPLAIN/docker/05-https-tls-termination.md` — nginx TLS terminator design
- `docs/EXPLAIN/docker/06-https-production-readiness.md` — HTTPS production checklist
- `docs/EXPLAIN/storage/01-s3-architecture.md` — S3/MinIO/R2 storage design
- `docs/EXPLAIN/redis-celery/02-celery-workers.md` — Celery worker configuration
