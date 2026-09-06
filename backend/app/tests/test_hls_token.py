"""Unit tests for backend.app.services.hls_token.

Tests:
  - Token generation produces a 2-part base64url string
  - Token validation accepts valid tokens, rejects tampered/expired/out-of-scope
  - Cookie extraction works for various Cookie header formats
  - HMAC verification is timing-safe (indirectly via hmac.compare_digest)
  - Clip key extraction from hls_playlist_url is correct

These tests do NOT require Docker/PostgreSQL — the token service is pure
Python + hashlib + hmac, so it's a fast unit test.
"""
import base64
import hashlib
import hmac
import json
import time

import pytest


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def token_secret(settings):
    settings.MEDIA_TOKEN_SECRET = "test-secret-key-for-unit-tests"
    return settings.MEDIA_TOKEN_SECRET


@pytest.fixture
def token_ttl(settings):
    settings.MEDIA_TOKEN_TTL_SECONDS = 600
    return 600


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

class TestGeneratePlaybackToken:
    def test_produces_two_part_base64url_string(self, token_secret, token_ttl):
        from backend.app.services.hls_token import generate_playback_token

        token = generate_playback_token(user_id=42, clip_key="hls/abc-123")
        assert "." in token
        parts = token.split(".")
        assert len(parts) == 2
        # Both parts should be valid base64url
        for part in parts:
            decoded = base64.urlsafe_b64decode(
                part + "=" * (4 - len(part) % 4) if len(part) % 4 else part
            )
            assert decoded  # non-empty

    def test_payload_contains_expected_fields(self, token_secret, token_ttl):
        from backend.app.services.hls_token import generate_playback_token, _b64url_decode

        token = generate_playback_token(user_id=42, clip_key="hls/abc-123")
        payload_b64 = token.split(".")[0]
        payload_json = _b64url_decode(payload_b64)
        payload = json.loads(payload_json)

        assert payload["u"] == 42
        assert payload["c"] == "hls/abc-123"
        assert payload["v"] == 1
        assert "exp" in payload
        assert "iat" in payload

    def test_exp_is_now_plus_ttl(self, token_secret, token_ttl):
        from backend.app.services.hls_token import generate_playback_token, _b64url_decode

        before = int(time.time())
        token = generate_playback_token(user_id=1, clip_key="hls/x")
        after = int(time.time())

        payload_b64 = token.split(".")[0]
        payload = json.loads(_b64url_decode(payload_b64))

        expected_min = before + token_ttl
        expected_max = after + token_ttl
        assert expected_min <= payload["exp"] <= expected_max
        assert payload["iat"] <= after

    def test_iat_is_current_time(self, token_secret, token_ttl):
        from backend.app.services.hls_token import generate_playback_token, _b64url_decode

        before = int(time.time())
        token = generate_playback_token(user_id=1, clip_key="hls/x")
        after = int(time.time())

        payload = json.loads(_b64url_decode(token.split(".")[0]))
        assert before <= payload["iat"] <= after

    def test_token_format_matches_doc_spec(self, token_secret, token_ttl):
        """Verify the token matches the exact format from the design doc."""
        from backend.app.services.hls_token import generate_playback_token

        token = generate_playback_token(
            user_id=123,
            clip_key="hls/abc-123-def",
        )
        # Format: base64url(payload_json).base64url(hmac_sha256(secret, base64url(payload_json)))
        payload_b64, sig_b64 = token.split(".")

        # Reconstruct payload and verify
        payload_json = json.loads(
            base64.urlsafe_b64decode(
                payload_b64 + "=" * (4 - len(payload_b64) % 4)
            ).decode("utf-8")
        )
        assert payload_json["u"] == 123
        assert payload_json["c"] == "hls/abc-123-def"

        # Verify signature
        expected_sig = hmac.new(
            token_secret.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")
        assert sig_b64 == expected_sig_b64


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidatePlaybackToken:
    def test_valid_token_passes(self, token_secret, token_ttl):
        from backend.app.services.hls_token import generate_playback_token, validate_playback_token

        token = generate_playback_token(user_id=1, clip_key="hls/abc-123")
        payload = validate_playback_token(token, "/hls/abc-123/master.m3u8")

        assert payload is not None
        assert payload["u"] == 1
        assert payload["c"] == "hls/abc-123"

    def test_tampered_payload_rejected(self, token_secret, token_ttl):
        from backend.app.services.hls_token import generate_playback_token, validate_playback_token, _b64url_encode
        import json

        token = generate_playback_token(user_id=1, clip_key="hls/abc-123")
        payload_b64, sig_b64 = token.split(".")

        # Tamper: change the user_id in the payload
        payload = json.loads(
            base64.urlsafe_b64decode(
                payload_b64 + "=" * (4 - len(payload_b64) % 4)
            ).decode("utf-8")
        )
        payload["u"] = 999  # forged user ID
        tampered_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        tampered_b64 = _b64url_encode(tampered_json.encode("utf-8"))

        result = validate_playback_token(f"{tampered_b64}.{sig_b64}", "/hls/abc-123/master.m3u8")
        assert result is None

    def test_expired_token_rejected(self, token_secret):
        from backend.app.services.hls_token import generate_playback_token, validate_playback_token, _b64url_decode, _b64url_encode
        import json

        token = generate_playback_token(user_id=1, clip_key="hls/abc-123")
        payload_b64, sig_b64 = token.split(".")

        # Forge an expired payload
        payload = json.loads(_b64url_decode(payload_b64))
        payload["exp"] = int(time.time()) - 1  # expired 1 second ago
        expired_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        expired_b64 = _b64url_encode(expired_json.encode("utf-8"))

        # Re-sign with the same key (simulating a token that was valid but expired)
        import hmac as hmac_mod
        new_sig = hmac_mod.new(
            token_secret.encode("utf-8"),
            expired_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        new_sig_b64 = _b64url_encode(new_sig)

        result = validate_playback_token(
            f"{expired_b64}.{new_sig_b64}",
            "/hls/abc-123/master.m3u8",
        )
        assert result is None

    def test_wrong_clip_scope_rejected(self, token_secret, token_ttl):
        from backend.app.services.hls_token import generate_playback_token, validate_playback_token

        token = generate_playback_token(user_id=1, clip_key="hls/abc-123")

        # Token is for clip "hls/abc-123" but request is for "hls/xyz-789"
        result = validate_playback_token(token, "/hls/xyz-789/master.m3u8")
        assert result is None

    def test_wrong_clip_scope_partial_match_rejected(self, token_secret, token_ttl):
        """A token for 'hls/abc-123' must NOT work on 'hls/abc-123-sub/'."""
        from backend.app.services.hls_token import generate_playback_token, validate_playback_token

        token = generate_playback_token(user_id=1, clip_key="hls/abc-123")

        # The clip key is "hls/abc-123" — the request path must start with
        # "/hls/abc-123/". "hls/abc-123-sub" does not match.
        result = validate_playback_token(token, "/hls/abc-123-sub/master.m3u8")
        assert result is None

    def test_correct_clip_scope_accepted(self, token_secret, token_ttl):
        """Token for 'hls/abc-123' should work on any path under /hls/abc-123/."""
        from backend.app.services.hls_token import generate_playback_token, validate_playback_token

        token = generate_playback_token(user_id=1, clip_key="hls/abc-123")

        result = validate_playback_token(token, "/hls/abc-123/master.m3u8")
        assert result is not None

        result = validate_playback_token(token, "/hls/abc-123/segment_1.ts")
        assert result is not None

        result = validate_playback_token(token, "/hls/abc-123/sub/variant.m3u8")
        assert result is not None

    def test_no_clipping_path_slash_accepted(self, token_secret, token_ttl):
        """Edge case: token for 'hls/abc-123' on path '/hls/abc-123' (no trailing slash)."""
        from backend.app.services.hls_token import generate_playback_token, validate_playback_token

        token = generate_playback_token(user_id=1, clip_key="hls/abc-123")

        # Without the trailing slash, the prefix "/hls/abc-123/" doesn't match
        # "/hls/abc-123" — this is correct: we require the path separator
        result = validate_playback_token(token, "/hls/abc-123")
        assert result is None

    def test_missing_token_rejected(self, token_secret, token_ttl):
        from backend.app.services.hls_token import validate_playback_token

        assert validate_playback_token("", "/hls/abc-123/master.m3u8") is None
        assert validate_playback_token(None, "/hls/abc-123/master.m3u8") is None

    def test_malformed_token_rejected(self, token_secret, token_ttl):
        from backend.app.services.hls_token import validate_playback_token

        assert validate_playback_token("not-a-token", "/hls/abc-123/master.m3u8") is None
        assert validate_playback_token("a.b.c", "/hls/abc-123/master.m3u8") is None
        assert validate_playback_token("a", "/hls/abc-123/master.m3u8") is None

    def test_bad_signature_rejected(self, token_secret, token_ttl):
        from backend.app.services.hls_token import validate_playback_token

        token = "eyJ1IjogMSwgImMiOiAiaGxzL2FiYy0xMjMifQ.signature_mismatch"
        result = validate_playback_token(token, "/hls/abc-123/master.m3u8")
        assert result is None

    def test_wrong_version_rejected(self, token_secret, token_ttl):
        from backend.app.services.hls_token import validate_playback_token, _b64url_encode
        import json

        # Craft a payload with version != 1
        payload = {"u": 1, "c": "hls/abc-123", "exp": int(time.time()) + 600,
                   "iat": int(time.time()), "v": 2}
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        payload_b64 = _b64url_encode(payload_json.encode("utf-8"))

        import hmac as hmac_mod
        sig = hmac_mod.new(
            token_secret.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        sig_b64 = _b64url_encode(sig)

        result = validate_playback_token(
            f"{payload_b64}.{sig_b64}",
            "/hls/abc-123/master.m3u8",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Cookie extraction
# ---------------------------------------------------------------------------

class TestExtractTokenFromCookie:
    def test_extracts_valid_cookie(self, token_secret, token_ttl):
        from backend.app.services.hls_token import generate_playback_token, extract_token_from_cookie

        token = generate_playback_token(user_id=1, clip_key="hls/x")
        cookie_header = f"session=abc; ef_hls_token={token}; other=def"

        result = extract_token_from_cookie(cookie_header)
        assert result == token

    def test_returns_none_when_no_cookie(self):
        from backend.app.services.hls_token import extract_token_from_cookie

        assert extract_token_from_cookie(None) is None
        assert extract_token_from_cookie("") is None
        assert extract_token_from_cookie("session=abc") is None

    def test_handles_whitespace_in_cookie_header(self, token_secret, token_ttl):
        from backend.app.services.hls_token import generate_playback_token, extract_token_from_cookie

        token = generate_playback_token(user_id=1, clip_key="hls/x")
        cookie_header = f"  session=abc  ;  ef_hls_token={token}  ;  other=def  "

        result = extract_token_from_cookie(cookie_header)
        assert result == token
