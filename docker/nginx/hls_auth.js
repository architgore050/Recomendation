/*
 * hls_auth.js — njs script for HLS token cookie validation (Option B: dev).
 *
 * STUB — not yet wired into nginx.conf. This file exists so that the
 * docker-compose.yml volume mount does not fail. When Option B ships,
 * replace this stub with the full implementation from:
 *   docs/EXPLAIN/storage/04-hls-token-protection.md#option-b--nginx--njs-development
 *
 * DECISION: Using njs (nginx JavaScript module) for HMAC cookie validation
 * instead of auth_request (which round-trips to Django for every segment).
 * The crypto.subtle Web Crypto API in njs performs HMAC-SHA256 verification
 * in-process, with no upstream round-trip per request.
 */
// export function validate(r) {
//   // Validate ef_hls_token cookie against MEDIA_TOKEN_SECRET
//   // If invalid: r.return(403)
//   // If valid: return (allow proxy_pass to MinIO)
// }
export {};
