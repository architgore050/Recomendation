"""HLS playback token service.

Generates short-lived, per-clip, user-bound HMAC tokens for HLS playback
access. The token is a signed cookie that browsers send automatically on
all HLS subrequests (master.m3u8, variant playlists, segments) — unlike
query-string signatures, cookies are not stripped by RFC 3986
relative-reference resolution (§5.2.2), which is why they are the only
viable token mechanism for multi-file HLS streams.

Token format:
    base64url(payload_json) . base64url(hmac_sha256(secret, payload_b64))

Payload (JSON, sorted keys for deterministic encoding):
    { "c": "hls/<clip_id>", "exp": int, "iat": int, "u": int, "v": 1 }

The validation counterparts live in:
  - workers/hls-token-worker/src/token.ts  (production Cloudflare Worker)
  - docker/nginx/hls_auth.js               (dev nginx + njs)

Both MUST match this file's algorithm exactly.

DECISION: Using HMAC-SHA256 with a symmetric key rather than JWT because:
  1. The Worker uses WebCrypto API (no JWT library dependency)
  2. Smaller token size than JWT (no base64 JSON header)
  3. Symmetric key is sufficient — issuer and validator share one secret
"""
import base64
import hashlib
import hmac
import json
import time

from django.conf import settings

COOKIE_NAME = "ef_hls_token"
TOKEN_VERSION = 1


def _get_secret() -> bytes:
    """Return the HMAC secret as bytes.

    SECURITY: Uses a dedicated env var (MEDIA_TOKEN_SECRET), not
    DJANGO_SECRET_KEY. The Worker and nginx must share this secret;
    they do NOT have access to Django's settings module.
    """
    secret = getattr(settings, "MEDIA_TOKEN_SECRET", "")
    if not secret:
        raise RuntimeError(
            "MEDIA_TOKEN_SECRET is not set — HLS token protection is "
            "unavailable. Set it in .env."
        )
    return secret.encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    """Base64url encode without padding (RFC 4648 §5)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Base64url decode, adding padding back if stripped."""
    padding = 4 - (len(data) % 4)
    if padding < 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def _ttl_seconds() -> int:
    """Return configured token TTL in seconds."""
    return int(getattr(settings, "MEDIA_TOKEN_TTL_SECONDS", 600))


def generate_playback_token(user_id: int, clip_key: str) -> str:
    """Generate a short-lived, per-clip HMAC token for HLS playback.

    Args:
        user_id: The authenticated Django user's ID. Bound into the token
            so the validator can confirm the user is still authorized
            (though the Worker/nginx only checks HMAC + expiry + scope,
            not live user state — that is enforced at the API issuance step).
        clip_key: The object storage key prefix for this clip's HLS output.
            Example: "hls/abc-123-def-456". This is the
            clip.hls_playlist_url with the trailing "master.m3u8" stripped.

    Returns:
        Token string: ``base64url(payload).base64url(signature)``
    """
    now = int(time.time())
    ttl = _ttl_seconds()
    payload = {
        "u": user_id,
        "c": clip_key,
        "exp": now + ttl,
        "iat": now,
        "v": TOKEN_VERSION,
    }
    # sort_keys=True ensures deterministic encoding across Python/TypeScript
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = _b64url_encode(payload_json.encode("utf-8"))

    signature = hmac.new(
        _get_secret(),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(signature)

    return f"{payload_b64}.{sig_b64}"


def validate_playback_token(token: str, request_path: str) -> dict | None:
    """Validate a playback token.

    Args:
        token: The token string (``payload_b64.signature_b64``).
        request_path: The full request path (e.g.
            ``/hls/abc-123/master.m3u8``). The token's ``c`` field defines
            an allowed prefix — the request path must start with
            ``/<clip_key>/``.

    Returns:
        The decoded payload dict if valid, ``None`` if the token is
        missing, malformed, expired, scope-mismatched, or has a bad
        signature.
    """
    if not token or "." not in token:
        return None

    parts = token.split(".")
    if len(parts) != 2:
        return None

    payload_b64, sig_b64 = parts

    # --- HMAC verification (timing-safe) ---
    try:
        received_sig = _b64url_decode(sig_b64)
    except Exception:
        return None

    expected_sig = hmac.new(
        _get_secret(),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(expected_sig, received_sig):
        return None

    # --- Payload decoding ---
    try:
        payload_json = _b64url_decode(payload_b64)
        payload = json.loads(payload_json)
    except Exception:
        return None

    # --- Version check ---
    if payload.get("v") != TOKEN_VERSION:
        return None

    # --- Expiry check ---
    if int(time.time()) > payload["exp"]:
        return None

    # --- Clip-scope check ---
    # The token's 'c' field is like "hls/abc-123".
    # The request path is like "/hls/abc-123/master.m3u8".
    # The request path must start with "/<clip_key>/".
    expected_prefix = "/" + payload["c"] + "/"
    if not request_path.startswith(expected_prefix):
        return None

    return payload


def extract_token_from_cookie(cookie_header: str) -> str | None:
    """Extract the ef_hls_token value from a Cookie header string.

    Args:
        cookie_header: The raw ``Cookie`` header value (e.g.
            "ef_hls_token=abc.def; session=ghi").

    Returns:
        The token string if found, ``None`` otherwise.
    """
    if not cookie_header:
        return None

    for pair in cookie_header.split(";"):
        pair = pair.strip()
        if pair.startswith(COOKIE_NAME + "="):
            return pair[len(COOKIE_NAME) + 1:]
    return None
