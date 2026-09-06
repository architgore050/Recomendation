# Laptop Media Worker Setup Guide

This document explains how to set up the laptop half of the hybrid deployment.

## Prerequisites

1. **Laptop** with Docker installed
2. **8+ GB RAM** (required for Whisper + SentenceTransformer + KeyBERT)
3. **Tailscale** installed on both laptop and VPS
4. **Stable internet connection** (for Tailscale tunnel to VPS)
5. **HuggingFace API token** (`HF_TOKEN`) — for building the media Docker image

## Step 1: Install Tailscale on Laptop

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Both the laptop and VPS must be on the same Tailscale tailnet. The VPS
must advertise the `172.28.0.0/16` subnet (see VPS setup guide), and you
must approve it in the Tailscale admin console.

## Step 2: Build the Media Image

The `media` Docker image bakes in HuggingFace models at build time (Whisper,
SentenceTransformer, KeyBERT). The `HF_TOKEN` is passed via BuildKit secret —
it never appears in the image layers.

```bash
git clone https://github.com/your-org/echoflow.git
cd echoflow
git checkout feat/hybrid-laptop
cp .env.laptop.example .env
# EDIT .env with real values:
#   - DJANGO_SECRET_KEY = same as VPS (must match!)
#   - DB_PASSWORD = same as VPS
#   - AWS_ACCESS_KEY_ID / SECRET = R2 credentials
#   - AWS_S3_ENDPOINT_URL = your R2 endpoint
#   - HF_TOKEN = your HuggingFace token
#   - FIELD_ENCRYPTION_KEY = same as VPS (must match!)

# Build the media image with the HuggingFace token as a build secret
export HF_TOKEN=hf_your_token_here
docker build --target media -t echoflow-media:local --secret id=hf_token,env=HF_TOKEN .
```

## Step 3: Start the Media Worker

```bash
bash scripts/laptop-deploy.sh
```

The script:
1. Validates `HF_TOKEN` is set
2. Checks Tailscale connectivity to VPS services
3. Builds the media image (if not already built)
4. Starts `celery_media` worker via `docker compose -f docker-compose.laptop.yml up -d`
5. Starts the heartbeat script in the background

The `celery_media` worker:
- Connects to the VPS Redis broker (`172.28.0.2:6379`) via Tailscale
- Connects to the VPS PostgreSQL (`172.28.0.4:5432`) via Tailscale
- Downloads original uploads from R2
- Runs Whisper transcription, acoustic/semantic vector extraction, KeyBERT tagging
- Encodes HLS segments and uploads to R2 `hls/{clip_id}/` prefix
- Updates `AudioClip` rows with HLS URL and status

## Step 4: Verify

```bash
# Check worker logs
docker compose -f docker-compose.laptop.yml logs -f celery_media

# Check heartbeat (should return {"media_worker_alive": true})
curl https://api.echo-flow.in/api/v1/health/media-worker/

# Upload a clip on the VPS, approve moderation, and watch the laptop process it
```

## Heartbeat Mechanism

The heartbeat is a simple background script that writes to the broker Redis:

```bash
nohup bash scripts/laptop-heartbeat.sh > /tmp/heartbeat.log 2>&1 &
```

Every 30 seconds, it writes:
```
SET media_worker:alive <unix_timestamp> EX 60
```

The API endpoint `GET /api/v1/health/media-worker/` reads this key:
- **Key exists** → `{"media_worker_alive": true}` (200)
- **Key missing** → `{"media_worker_alive": false}` (200)
- **Redis unreachable** → `{"media_worker_alive": false}` (503)

If the script stops (laptop asleep, Tailscale disconnects), the key expires
after 60 seconds and the API correctly reports the worker as offline.

## Resource Usage

| Component | Estimated RAM |
|-----------|--------------|
| Whisper model (baked in image) | ~1.5 GB |
| SentenceTransformer model | ~500 MB |
| KeyBERT + librosa + Python runtime | ~200 MB |
| ffmpeg + audio scratch space | ~500 MB |
| Docker overhead | ~300 MB |
| **Total** | **~2.5-3 GB resident** |

The compose file limits `celery_media` to 4 GB with `--pool=prefork
--concurrency=2`. This means at most 2 clips are processed simultaneously,
each using ~2 GB.

## Troubleshooting

### Worker can't connect to Redis

```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Fix:** Verify Tailscale is running and the VPS subnet is approved:
```bash
tailscale ip  # Show your Tailscale IP
ping 172.28.0.2  # Test connectivity to VPS Redis
```

### R2 upload fails

```
botocore.exceptions.EndpointConnectionError
```

**Fix:** Check `AWS_S3_ENDPOINT_URL` in `.env`. It must be the full R2 URL:
`https://<accountid>.r2.cloudflarestorage.com`

### Models not found

```
OSError: Fetched 1 files but failed to do so
```

**Fix:** The media image was built without `HF_TOKEN`, so models weren't
baked in. Rebuild with the secret:
```bash
export HF_TOKEN=hf_your_token_here
docker build --target media -t echoflow-media:local --secret id=hf_token,env=HF_TOKEN .
```
