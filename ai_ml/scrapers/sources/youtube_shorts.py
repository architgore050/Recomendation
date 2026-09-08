"""YouTube Shorts connector via yt-dlp.

Uses the same `yt-dlp` dep as the youtube connector. Shorts are
identified by URL pattern (youtube.com/shorts/<id>) and constrained
to short durations (default ≤ 90s, the YouTube Shorts cap).

License: same as the youtube connector — UNKNOWN, gated by the
central license_allows_commercial() check. The operator can target
CC content by search query (e.g. "creative commons shorts").
"""
import logging

from . import youtube as _youtube_base

logger = logging.getLogger(__name__)

SOURCE_NAME = 'youtube_shorts'
DEFAULT_SEARCH_QUERY = 'creative commons short'
DEFAULT_MAX_DURATION_S = 90  # Shorts cap


def fetch_audio(limit=10, search_query=None, max_duration_s=None,
                page=1, sort='identifier asc'):
    """Search YouTube Shorts.

    Reuses the YouTube connector's yt-dlp plumbing. Two differences:
    - DEFAULT_MAX_DURATION_S = 90s (vs. 600s for full videos)
    - Search query biased toward Shorts content

    Returns list of dicts (same contract as the YouTube connector).
    """
    q = search_query or DEFAULT_SEARCH_QUERY
    max_dur = max_duration_s if max_duration_s is not None else DEFAULT_MAX_DURATION_S
    items = _youtube_base.fetch_audio(
        limit=limit, search_query=f'{q} #shorts',
        max_duration_s=max_dur, page=page, sort=sort,
    )
    # Mark each item as a Shorts source so the downloader / uploader
    # can use a different naming convention if needed.
    for it in items:
        it['_source_kind'] = 'youtube_shorts'
        it['source_name'] = SOURCE_NAME
    return items


def extract_stream_url(item, max_bytes=None):
    """Same as youtube.extract_stream_url; the URL pattern is identical
    (youtube.com/shorts/<id> resolves via the same /watch?v= form)."""
    return _youtube_base.extract_stream_url(item, max_bytes=max_bytes)
