import logging
from .internet_archive import ia_search_raw, _ia_resolve_audio_url
from ..base import normalize_license

logger = logging.getLogger(__name__)


def fetch_audio(limit=10, max_file_size=None, page=1, sort='identifier asc'):
    """Fetch Library of Congress historical audio via the IA mirror.

    HACK: The LOC's own JSON API requires API key registration. The LOC
    National Jukebox catalog (pre-1923 PD recordings) is mirrored on
    Internet Archive primarily as the `78rpm` collection (309k+ cylinder
    and 78-rpm recordings, pre-1928, all PD). We filter by uploader=
    'Library of Congress' OR subject mentions 'Library of Congress' to
    surface LOC-cataloged items specifically; falling back to the broader
    78rpm collection if that yields nothing.
    """
    query = ('mediatype:(audio) AND '
             'collection:("78rpm") AND '
             '(uploader:("Library of Congress") OR '
             ' subject:("Library of Congress") OR '
             ' subject:("national jukebox"))')
    docs = ia_search_raw(query, limit=limit, page=page, sort=sort)
    if not docs:
        docs = ia_search_raw(
            'mediatype:(audio) AND collection:("78rpm")',
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
            'source_collection': '78rpm',
        })
        if len(results) >= limit:
            break
    return results