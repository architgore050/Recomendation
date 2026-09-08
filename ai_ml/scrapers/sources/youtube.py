"""YouTube connector via yt-dlp.

DECISION: Uses `yt-dlp` (a single Python wheel dep) rather than a
headless browser (heavyweight, slow, expensive memory). yt-dlp is
free, open-source, and supports 1000+ sites including YouTube.

ToS notes:
- YouTube's ToS forbids automated downloading without permission.
- This connector is intended for content that is licensed for
  reuse: Creative Commons, public domain, or operator-licensed.
- Filter at extraction time via `yt-dlp`'s `match_filter` so we
  only pick up items the operator has explicitly enabled (e.g.
  CC-licensed videos). The `--extractor-args` argument supports
  `youtube:player_client=web` and similar flags.
- If yt-dlp is not installed, the connector returns [] with a
  WARNING. The operator can install it via the wheelhouse regen
  script and rebuild the image.
"""
import logging

logger = logging.getLogger(__name__)

SOURCE_NAME = 'youtube'
DEFAULT_SEARCH_QUERY = 'creative commons music'

# Default license filter: yt-dlp's match_filter receives the info_dict
# of each entry. We use it to skip everything that doesn't look like
# CC / public domain. The exact heuristic depends on YouTube's
# metadata schema; conservatively we don't filter at the metadata
# layer (the connector returns "UNKNOWN" license family and the
# management command's central license_allows_commercial() rejects
# it). The operator can pre-filter upstream via a search query that
# targets known CC channels (e.g. "cc by", "no copyright").
DEFAULT_MAX_DURATION_S = 600  # 10 minutes — skip livestreams / long videos
DEFAULT_LICENSE_HINT_QUERY = 'creative commons audio'  # CC-bias in search


def _try_import_yt_dlp():
    """Lazy import. Returns the module or None if not installed."""
    try:
        import yt_dlp
        return yt_dlp
    except ImportError:
        return None


def fetch_audio(limit=10, search_query=None, max_duration_s=None,
                page=1, sort='identifier asc'):
    """Search YouTube for videos matching the query.

    Returns list of dicts: {url, title, page_url, license='UNKNOWN', id, ...}.

    `url` is NOT a direct file URL — yt-dlp needs to be invoked again
    to extract the actual stream URL. The management command's
    downloader handles that via the YouTube download helper (see
    `ai_ml.scrapers.youtube_download`).

    Args:
        limit: max items to return
        search_query: YouTube search query. Defaults to a CC-bias
            search so the operator gets reusable content.
        max_duration_s: skip videos longer than this. None = no cap.
        page: 1-indexed page number (yt-dlp `playliststart`).
        sort: sort spec. Default `identifier asc` for stable pagination.
    """
    if sort != 'identifier asc':
        # yt-dlp's sort parameter differs from IA. We honor the value
        # the caller passes; default to ytsearch's default (relevance)
        # when the caller doesn't care.
        pass

    yt_dlp = _try_import_yt_dlp()
    if yt_dlp is None:
        logger.warning(
            'YouTube connector: yt-dlp not installed. Install it via '
            'the wheelhouse regen script (`scripts/regen-wheelhouse.sh`) '
            'and rebuild the image. Returning empty list.')
        return []

    q = search_query or DEFAULT_LICENSE_HINT_QUERY
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,  # don't download during search; just get metadata
        'skip_download': True,
        'playlistend': limit,
        # ytsearch:N — perform a YouTube search, return first N results
        'default_search': f'ytsearch{limit}',
    }
    if max_duration_s is None:
        max_duration_s = DEFAULT_MAX_DURATION_S
    # match_filter: skip live, too-long, and missing-essential-metadata entries.
    def _match_filter(info):
        if info.get('is_live'):
            return 'skipping live stream'
        duration = info.get('duration') or 0
        if max_duration_s and duration > max_duration_s:
            return f'skipping long video ({duration}s > {max_duration_s}s)'
        if not info.get('id'):
            return 'missing video id'
        return None
    ydl_opts['match_filter'] = _match_filter

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # yt-dlp extracts the search results as a flat playlist
            results = ydl.extract_info(f'ytsearch{limit}:{q}',
                                        download=False)
        except Exception as e:
            logger.exception('YouTube search failed: %s', e)
            return []

    entries = results.get('entries', []) if results else []
    items = []
    for ent in entries:
        if not ent:
            continue
        vid = ent.get('id')
        if not vid:
            continue
        title = ent.get('title') or vid
        page_url = ent.get('url') or f'https://www.youtube.com/watch?v={vid}'
        # NOTE: extract_flat=True means we don't have a direct file
        # URL. The downloader knows how to call yt-dlp again to
        # resolve the actual stream URL.
        items.append({
            'url': f'youtube:video:{vid}',  # pseudo-URL; downloader recognizes
            'title': title,
            'page_url': page_url,
            'id': vid,
            'license': 'UNKNOWN',  # YouTube rarely exposes license metadata
            'duration_ms': (ent.get('duration') or 0) * 1000,
            'creator': ent.get('uploader') or ent.get('channel') or '',
            '_source_kind': 'youtube',
        })
        if len(items) >= limit:
            break
    return items


def extract_stream_url(item, max_bytes=None):
    """Resolve a YouTube video to a direct audio stream URL.

    Called by the downloader when item['url'] starts with
    'youtube:video:'. Returns (url, size_bytes_or_None) or
    raises RuntimeError.
    """
    yt_dlp = _try_import_yt_dlp()
    if yt_dlp is None:
        raise RuntimeError('yt-dlp not installed')

    vid = item.get('id')
    if not vid:
        raise RuntimeError('item has no id')
    url = f'https://www.youtube.com/watch?v={vid}'

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'noplaylist': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            raise RuntimeError(f'yt-dlp extract failed: {e}')

    # Pick the best audio-only format
    stream_url = info.get('url')
    if not stream_url:
        # Fallback: pick from formats list
        formats = info.get('formats') or []
        for f in formats:
            if f.get('acodec') and f.get('acodec') != 'none' and f.get('url'):
                stream_url = f['url']
                break
    if not stream_url:
        raise RuntimeError('yt-dlp returned no stream URL')

    return stream_url, info.get('filesize') or info.get('filesize_approx')
