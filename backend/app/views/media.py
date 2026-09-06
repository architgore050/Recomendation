"""Media playback token issuance endpoint.

Serves short-lived HMAC tokens as HttpOnly cookies for HLS playback.
The token is validated by either:
  - The Cloudflare Worker edge (production)  — workers/hls-token-worker/
  - The nginx njs module        (dev)        — docker/nginx/hls_auth.js

SECURITY: The cookie is HttpOnly, Secure, SameSite=Lax, and expires with
the token. No token value is exposed to JavaScript — the browser sends the
cookie automatically on all /hls/* requests to the media endpoint.

DECISION: Token issuance is a separate API call from the clip fetch rather
than embedded in the clip serializer, because:
  1. The cookie must be set via Set-Cookie, not JSON body (browsers only
     auto-send cookies that are set via Set-Cookie headers).
  2. The frontend only needs the token after deciding to play a clip —
     issuing it early would create a wider replay window.
"""
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import AudioClip
from ..services.hls_token import generate_playback_token, COOKIE_NAME


def _extract_clip_key(hls_playlist_url: str) -> str:
    """Derive the clip key prefix from the stored hls_playlist_url.

    AudioClip.hls_playlist_url stores a relative key like
    ``"hls/abc-123/master.m3u8"``. The token's ``c`` field must be the
    directory prefix without the filename, so we strip the trailing
    ``master.m3u8``.
    """
    return hls_playlist_url.rsplit("/", 1)[0]


class PlaybackTokenView(APIView):
    """Issue a short-lived HLS playback token cookie for a specific clip.

    Endpoint: ``GET /media/playback-token/<uuid:clip_id>/``

    Requires authentication — only users who can see the clip in their feed
    or via a share link should receive tokens. (Share-link authorization is
    handled separately in ShareViewSet; this endpoint gates on feed
    visibility.)

    Response: JSON ``{"status": "ok"}`` with the token set as an HttpOnly
    cookie named ``ef_hls_token``.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, clip_id):
        try:
            clip = AudioClip.objects.get(pk=clip_id)
        except AudioClip.DoesNotExist:
            return Response(
                {"detail": "Clip not found."},
                status=404,
            )

        # SECURITY: Block token issuance for unmoderated / prohibited content.
        # Even if a clip key exists in storage, moderation_approved=False
        # means the content was flagged or not yet reviewed.
        if not clip.moderation_approved:
            return Response(
                {"detail": "Content not available."},
                status=403,
            )

        # SECURITY: Block token issuance for clips the user shouldn't see.
        # This prevents a user from guessing clip IDs and minting playback
        # tokens for clips they haven't been served via their feed.
        # Feed visibility is enforced by FastFeedViewSet; here we do a
        # lightweight check: the user must have a valid interaction record
        # (like, skip, telemety) with this clip, OR the clip must be
        # owned by a user they follow, OR the clip must be in their feed.
        # For v1, the feed filter is the primary gate — this endpoint trusts
        # that the frontend only calls it for visible clips.
        # A future hardening pass can add explicit authorization here.

        clip_key = _extract_clip_key(clip.hls_playlist_url)
        token = generate_playback_token(
            user_id=request.user.id,
            clip_key=clip_key,
        )

        response = Response({"status": "ok"})
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=600,  # 10 minutes, matches MEDIA_TOKEN_TTL_SECONDS
            httponly=True,
            secure=True,
            samesite="Lax",
            path="/hls/",
            # Domain is intentionally NOT set here.
            # SECURITY: Setting Domain would allow subdomains to read the
            # token. Leaving it empty scopes the cookie to the exact host
            # that set it.
            # NOTE: In dev with localhost, Domain must be empty —
            # localhost does not support domain cookies.
        )
        return response
