import logging
from ..base import get_session, normalize_license

logger = logging.getLogger(__name__)

API = 'https://api.openverse.org/v1/audio/'
SOURCE_NAME = 'openverse'


def _build_headers():
    """Return auth headers when OPENVERSE_API_KEY is set, else empty dict.

    Openverse supports anonymous access with 20/min burst / 200/day sustained.
    A registered API key raises the per-minute burst. We surface the key as
    `Authorization: Bearer <key>` per Openverse docs (works on either path).
    """
    from django.conf import settings
    key = getattr(settings, 'SCRAPER_OPENVERSE_API_KEY', '') or ''
    if not key:
        return {}
    return {'Authorization': f'Bearer {key}'}


def fetch_audio(limit=10, category=None, license_excludes_nc=False):
    """Search Openverse for audio items.

    Args:
        limit: max items to return
        category: optional Openverse category filter (music, audiobook,
                  news, podcast, pronunciation, sound_effect)
        license_excludes_nc: when True, restrict to non-NC licenses via
                  Openverse's license= filter.

    Returns:
        list of dicts: {url, title, page_url, license, id, ...extras}
    """
    params = {
        'q': '',
        'page_size': min(int(limit), 100),
        'license': 'by,sa,cc0' if license_excludes_nc else '',
    }
    if category:
        params['category'] = category
    # Drop empty params so Openverse doesn't 400 on blank values
    params = {k: v for k, v in params.items() if v != ''}

    try:
        resp = get_session().get(API, params=params,
                                  headers=_build_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        # One-line summary only; full traceback available via Django
        # debug logging. The earlier management-command retry loop
        # already logged the chained details.
        logger.warning('Openverse fetch failed: %s', e.__class__.__name__)
        return []

    results = []
    for r in data.get('results', [])[:limit]:
        url = r.get('url')
        if not url:
            continue
        raw_lic = r.get('license') or ''
        # Openverse returns lowercase shorts like 'by', 'by-nc', 'cc0'.
        # normalize_license() converts to CC-BY, CC-BY-NC, CC0.
        family = normalize_license(raw_lic)
        results.append({
            'url': url,
            'title': r.get('title') or '',
            'page_url': r.get('foreign_landing_url') or url,
            'license': family,
            'license_raw': raw_lic,
            'license_url': r.get('license_url') or '',
            'id': r.get('id'),
            'creator': r.get('creator') or '',
            'provider': r.get('provider') or '',
            'category': r.get('category') or '',
            'duration_ms': r.get('duration'),
            'attribution': r.get('attribution') or '',
        })
    return results