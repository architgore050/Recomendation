import logging
from .internet_archive import ia_search_raw, _ia_resolve_audio_url
from ..base import normalize_license

logger = logging.getLogger(__name__)


def fetch_audio(limit=10, max_file_size=None, page=1, sort='identifier asc'):
    """Fetch BBC Sound Effects (RemArc-NC license).

    The BBC SFX archive is mirrored on Internet Archive as a single mega-item
    `BBCSoundEffectsComplete` plus several BBC-sourced uploads. They are
    filtered via `creator:"BBC" AND subject:(sound-effects OR sfx)`. All
    items are non-commercial only (RemArc-NC) — every item is tagged
    `is_noncommercial=True` by the management command via the family
    normalization.

    SECURITY: Default behavior is to import these items but the runtime gate
    (SCRAPER_ALLOW_NC env var) decides whether they reach user feeds. By
    default the gate is OFF — items still get scraped into the catalog for
    audit/compliance but are filtered out of feed queries.

    Args:
        limit: max items to return
        max_file_size: when set, items whose smallest playable file exceeds
            this byte count are filtered out (used by smoke to avoid 1GB
            downloads on slow connections).
        page: 1-indexed IA advancedsearch page; combined with `sort` makes
            resume deterministic.

    Returns list of dicts: {url, title, page_url, license='REMARC-NC', id}.
    """
    query = ('mediatype:(audio) AND '
             'creator:("BBC") AND '
             'subject:(sound-effects OR sfx)')
    docs = ia_search_raw(query, limit=limit, page=page, sort=sort)
    if not docs:
        docs = ia_search_raw(
            'identifier:("BBCSoundEffectsComplete") AND mediatype:(audio)',
            limit=limit, page=page, sort=sort)

    results = []
    for d in docs:
        identifier = d.get('identifier')
        if not identifier:
            continue
        # Bounded-time metadata fetch: IA's BBC mega-items have 50+ audio
        # files; the slowest ones (300+ files) take 5s+. For smoke we need
        # the smallest playable file. Cap to 10s to avoid hanging.
        try:
            if max_file_size:
                url, size = _ia_resolve_audio_url(identifier, max_bytes=max_file_size)
            else:
                url, _ = _ia_resolve_audio_url(identifier)
        except Exception as e:
            logger.warning('bbc_sound_effects: metadata failed for %s: %s', identifier, e)
            continue
        if not url:
            continue
        title = d.get('title') or identifier
        if isinstance(title, list):
            title = title[0] if title else identifier
        results.append({
            'url': url,
            'title': title,
            'page_url': f'https://archive.org/details/{identifier}',
            'id': identifier,
            'license': normalize_license('RemArc-NC'),
            'license_raw': 'RemArc-NC',
            'creator': d.get('creator') or 'BBC',
            'is_noncommercial': True,
        })
        if len(results) >= limit:
            break
    return results