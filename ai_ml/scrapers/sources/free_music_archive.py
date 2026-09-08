import logging
from .internet_archive import ia_search_raw, _ia_resolve_audio_url
from ..base import normalize_license

logger = logging.getLogger(__name__)


def fetch_audio(limit=10, max_file_size=None, page=1, sort='identifier asc'):
    """Fetch Free Music Archive items via the IA mirror.

    HACK: FMA's official API v2 has been intermittently unavailable since 2024.
    The Free Music Archive catalog is mirrored on Internet Archive; items are
    not in a single `collection:` but tagged with subject="free music" +
    licenseurl=creativecommons. We query IA with those metadata filters.

    `page` + `sort` enable resumable pagination — see base.py / state.
    """
    query = ('mediatype:(audio) AND '
             'licenseurl:*creativecommons* AND '
             'subject:"free music"')
    docs = ia_search_raw(query, limit=limit, page=page, sort=sort)

    results = []
    for d in docs:
        identifier = d.get('identifier')
        if not identifier:
            continue
        if max_file_size:
            url, _ = _ia_resolve_audio_url(identifier, max_bytes=max_file_size)
        else:
            url, _ = _ia_resolve_audio_url(identifier)
        if not url:
            continue
        lic = d.get('licenseurl')
        if isinstance(lic, list):
            lic = lic[0] if lic else None
        family = normalize_license(lic or '')
        title = d.get('title') or identifier
        if isinstance(title, list):
            title = title[0] if title else identifier
        results.append({
            'url': url,
            'title': title,
            'page_url': f'https://archive.org/details/{identifier}',
            'id': identifier,
            'license': family,
            'licenseurl': lic or '',
            'creator': d.get('creator') or '',
        })
        if len(results) >= limit:
            break
    return results