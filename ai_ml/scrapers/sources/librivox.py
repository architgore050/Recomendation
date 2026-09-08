import logging
import requests
from ..base import get_session

logger = logging.getLogger(__name__)

API = 'https://librivox.org/api/feed/audiobooks'


def fetch_audio(limit=10, max_file_size=None, page=1, sort='id asc'):
    """Fetch LibriVox audiobooks via the official JSON API.

    LibriVox is all Public Domain (the underlying texts are pre-1927 works
    read aloud by volunteers). For each audiobook we resolve the Internet
    Archive identifier (every LibriVox item is mirrored on IA) and pick the
    smallest MP3 file as the chapter/track URL.

    `page` is a no-op for LibriVox's API (it uses `limit`+`offset`); kept
    in the signature for source-agnostic paginated iteration. `sort` is
    also a no-op (LibriVox returns most-recent-first by default).
    """
    params = {
        'format': 'json',
        'limit': min(int(limit) * 2, 50),  # overfetch
        'extended': 1,  # Required for url_iarchive, authors, etc.
    }
    try:
        resp = get_session().get(API, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.ConnectionError as e:
        logger.warning('LibriVox API failed: %s — %s',
                       e.__class__.__name__, str(e)[:200])
        return []
    except Exception as e:
        logger.warning('LibriVox API failed: %s', e.__class__.__name__)
        return []

    books = data.get('books', [])
    results = []
    for book in books:
        identifier = book.get('url_iarchive')
        title = book.get('title') or 'Untitled'
        if isinstance(title, list):
            title = title[0] if title else 'Untitled'
        iarchive_id = None
        if identifier:
            iarchive_id = identifier.rstrip('/').split('/')[-1]
        if not iarchive_id:
            continue
        url = _ia_first_mp3_url(iarchive_id, max_bytes=max_file_size)
        if not url:
            continue
        creators = book.get('authors') or []
        creator = ''
        if isinstance(creators, list) and creators:
            first = creators[0]
            if isinstance(first, dict):
                creator = (first.get('first_name', '') + ' ' +
                           first.get('last_name', '')).strip()
            else:
                creator = str(first)
        results.append({
            'url': url,
            'title': title,
            'page_url': book.get('url_librivox') or f'https://archive.org/details/{iarchive_id}',
            'license': 'CC0',
            'id': book.get('id') or iarchive_id,
            'creator': creator,
            'language': book.get('language') or '',
            'copyright_year': book.get('copyright_year'),
        })
        if len(results) >= limit:
            break
    return results


def _ia_first_mp3_url(identifier, max_bytes=None):
    """Resolve a single IA item to its first playable MP3 URL.

    Optional `max_bytes` returns None when the smallest playable file
    exceeds that cap. Lets the smoke test pre-reject items that would
    otherwise take minutes to download.
    """
    from .internet_archive import _ia_resolve_audio_url
    url, size = _ia_resolve_audio_url(identifier, max_bytes=max_bytes)
    return url