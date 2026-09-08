import logging
from .internet_archive import ia_search_raw, _ia_resolve_audio_url
from ..base import normalize_license

logger = logging.getLogger(__name__)


def fetch_audio(limit=10, max_file_size=None, page=1, sort='identifier asc'):
    """Fetch US-government audio (C-SPAN, NASA, USGS) via IA mirror.

    US government works are Public Domain by 17 U.S.C. § 105. The IA
    mirrors live under a mix of creator: and uploader: tags. We fan out
    across C-SPAN (creator="C-SPAN" OR "CSPAN"), NASA (creator="NASA"),
    and USGS (creator="USGS" OR "U.S. Geological Survey") in one round-trip
    per source.

    HACK: C-SPAN's own streaming endpoints are mostly Flash-era HLS that
    requires scraping the embedded player. The IA mirror is the canonical
    public source for these recordings where available.
    """
    per_source = max(1, int(limit) // 3)
    sources = {
        'cspan': ('mediatype:(audio) AND '
                  '(creator:("C-SPAN") OR creator:("CSPAN") OR title:cspan)'),
        'nasa': 'mediatype:(audio) AND creator:("NASA")',
        'usgs': ('mediatype:(audio) AND '
                 '(creator:("USGS") OR creator:("U.S. Geological Survey"))'),
    }

    all_docs = []
    for source_name, query in sources.items():
        docs = ia_search_raw(query, limit=per_source, page=page, sort=sort)
        for d in docs:
            d['_source'] = source_name
        all_docs.extend(docs)

    all_docs = all_docs[:limit]

    results = []
    for d in all_docs:
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
            'source_collection': d.get('_source') or '',
        })
    return results