import logging
from .internet_archive import ia_search_raw, _ia_resolve_audio_url
from ..base import normalize_license

logger = logging.getLogger(__name__)


def fetch_audio(limit=10, max_file_size=None, page=1, sort='identifier asc'):
    """Fetch Musopen classical recordings via the IA mirror.

    HACK: Musopen's official website has no API and the HTML page layout
    changes frequently. The classical catalog is mirrored on Internet Archive
    under the `musopen` collection. Items are pre-1927 public-domain
    recordings; license family is CC0.

    Note: Musopen IA items often only expose ZIP archives (not individual
    tracks). The downloader can't unzip on the fly, so most items will
    be filtered out by _ia_resolve_audio_url. This connector is best-effort;
    if it returns 0 items, the items are still accessible by downloading
    the ZIP manually and importing via the `kaggle` local-path connector.
    """
    docs = ia_search_raw('mediatype:(audio) AND collection:("musopen")',
                          limit=limit, page=page, sort=sort)

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
        title = d.get('title') or identifier
        if isinstance(title, list):
            title = title[0] if title else identifier
        results.append({
            'url': url,
            'title': title,
            'page_url': f'https://archive.org/details/{identifier}',
            'id': identifier,
            'license': normalize_license('CC0'),
            'creator': d.get('creator') or '',
        })
        if len(results) >= limit:
            break
    return results