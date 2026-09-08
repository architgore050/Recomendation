"""Pixabay Music + SFX connector.

DISABLED: This source is commented out in `ai_ml/scrapers/sources/__init__.py`
pending configuration of SCRAPER_PIXABAY_API_KEY. To re-enable:
1. Set SCRAPER_PIXABAY_API_KEY=<your-key> in .env
2. Uncomment the `pixabay` import and `'pixabay': pixabay` entry in __init__.py
3. Uncomment `'pixabay'` in SCRAPER_SOURCES in backend/EchoFlow/settings.py
"""
import logging
from django.conf import settings
from ..base import get_session, normalize_license

logger = logging.getLogger(__name__)

API = 'https://pixabay.com/api/'


def fetch_audio(limit=10, search_query='music'):
    """Fetch Pixabay Music + SFX items.

    Pixabay requires an API key (free tier: 5,000 req/hour). When the key
    is absent we return an empty list with a WARNING — same pattern as the
    Freesound connector.

    Returns list of dicts: {url, title, page_url, license='PIXABAY', id}.
    """
    api_key = getattr(settings, 'SCRAPER_PIXABAY_API_KEY', '') or ''
    if not api_key:
        logger.warning('Pixabay API key not configured (SCRAPER_PIXABAY_API_KEY); skipping')
        return []

    params = {
        'key': api_key,
        'q': search_query,
        'per_page': min(int(limit), 200),
    }
    try:
        resp = get_session().get(API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.exception('Pixabay fetch failed: %s', e)
        return []

    results = []
    for hit in data.get('hits', [])[:limit]:
        url = hit.get('audio') or ''
        if not url:
            continue
        results.append({
            'url': url,
            'title': hit.get('tags') or hit.get('user') or 'pixabay',
            'page_url': hit.get('pageURL') or '',
            'license': normalize_license('Pixabay'),
            'id': str(hit.get('id')),
            'creator': hit.get('user') or '',
            'duration_ms': hit.get('duration'),
        })
    return results