// EchoFlow HLS Token Worker — Token Validation Logic
//
// This file MUST produce/validate tokens using the EXACT same algorithm as
// backend/app/services/hls_token.py (Django). Any divergence means tokens
// issued by Django will fail validation in the Worker (or vice versa).
//
// Token format: base64url(payload_json).base64url(hmac_sha256(secret, base64url(payload_json)))
//
// Payload:
//   { u: number, c: string, exp: number, iat: number, v: 1 }
//   u   = user_id
//   c   = clip key prefix (e.g. "hls/abc-123")  — per-clip scope
//   exp = expiry epoch (seconds)
//   iat = issued-at epoch (seconds)
//   v   = token version

// --- STUB — implementation goes here when Option A ships ---
// Copy from docs/EXPLAIN/storage/04-hls-token-protection.md
// src/token.ts section for the full implementation.

export {};
