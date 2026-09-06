// EchoFlow HLS Token Worker — fetch handler
//
// Validates the ef_hls_token cookie on every /hls/* request and proxies
// to R2 if valid. See src/token.ts for validation logic and the full
// design in docs/EXPLAIN/storage/04-hls-token-protection.md.

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // --- STUB — full implementation in docs/EXPLAIN/storage/04-hls-token-protection.md ---
    return new Response('Not yet implemented — see 04-hls-token-protection.md', { status: 501 });
  },
};

interface Env {
  HLS_BUCKET: R2Bucket;
  MEDIA_TOKEN_SECRET: string;
}
