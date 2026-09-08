"""Podcast Index connector.

DISABLED: This source is commented out in `ai_ml/scrapers/sources/__init__.py`
pending configuration of SCRAPER_PODCAST_INDEX_API_KEY + SCRAPER_PODCAST_INDEX_API_SECRET.
To re-enable:
1. Set SCRAPER_PODCAST_INDEX_API_KEY=<key> and SCRAPER_PODCAST_INDEX_API_SECRET=<secret> in .env
2. Uncomment the `podcast_index` import and `'podcast_index': podcast_index` entry in __init__.py
3. Uncomment `'podcast_index'` in SCRAPER_SOURCES in backend/EchoFlow/settings.py
"""
import hmac
import logging
import time
import hashlib
from django.conf import settings
from ..base import get_session, resolve_podcast_rss

logger = logging.getLogger(__name__)

API = 'https://api.podcastindex.org/api/1.0/search'


def _auth_headers():
    """Build Podcast Index API auth headers.

    Podcast Index requires X-Auth-Key (key) + X-Auth-Date (unix timestamp) +
    X-Auth-Sig (HMAC-SHA256 signature) + User-Agent.
    """
    api_key = getattr(settings, 'SCRAPER_PODCAST_INDEX_API_KEY', '') or ''
    api_secret = getattr(settings, 'SCRAPER_PODCAST_INDEX_API_SECRET', '') or ''
    if not api_key or not api_secret:
        return None
    ts = str(int(time.time()))
    sig = hmac.new(
        f"{api_key}{ts}".encode('utf-8'),  # nosec: B104 -- HMAC-SHA256 for Podcast Index API request signing, not password hashing
        f"{api_key}{ts}".encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    headers = {
        'X-Auth-Key': api_key,
        'X-Auth-Date': ts,
        'X-Auth-Sig': sig,
        'User-Agent': 'EchoFlowScraper/1.0',
    }
    return headers


def fetch_audio(limit=10, search_query='technology'):
    """Fetch podcasts + episodes from Podcast Index.

    Two-step:
      1. Hit /search?term=<q>&type=lightning to discover feeds.
      2. For each feed, resolve the RSS via resolve_podcast_rss() to get
         episode-level audio enclosures.

    Returns list of dicts: {url, title, page_url, license='UNKNOWN', id}.
    License is UNKNOWN here — per-show license is set at the moderation layer.
    """
    headers = _auth_headers()
    if not headers:
        logger.warning('Podcast Index API key/secret not configured; skipping')
        return []

    params = {
        'q': search_query,
        'type': 'lightning',
        'max': str(min(int(limit), 1000)),
    }
    try:
        resp = get_session().get(API, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.exception('Podcast Index search failed: %s', e)
        return []

    feeds = data.get('feeds') or []
    results = []
    per_feed_cap = max(1, int(limit) // max(1, len(feeds))) if feeds else 0
    for feed in feeds:
        if per_feed_cap <= 0:
            break
        feed_url = feed.get('url')  # RSS feed URL
        if not feed_url:
            continue
        episodes = resolve_podcast_rss(feed_url, limit=per_feed_cap)
        for ep in episodes:
            ep['feed_title'] = feed.get('title') or ''
            ep['feed_id'] = feed.get('id')
            results.append(ep)
        if len(results) >= limit:
            break
    return results[:limit]