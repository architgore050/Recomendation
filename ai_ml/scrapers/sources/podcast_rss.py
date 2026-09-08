"""Generic podcast RSS resolver.

Wraps `ai_ml.scrapers.base.resolve_podcast_rss` so it can be invoked as a
source connector for ad-hoc podcast URLs. Usage:
    python manage.py scrape_audio --source=podcast_rss --feed=<rss-url>

Not registered in SOURCES by default; intended for on-demand resolution.
"""
import logging
from ..base import get_session, resolve_podcast_rss

logger = logging.getLogger(__name__)

DEFAULT_FEED = 'https://feeds.npr.org/510289/podcast.xml'


def fetch_audio(limit=10):
    """Resolve a single RSS feed.

    The feed URL is read from `SCRAPER_PODCAST_RSS_DEFAULT` env var
    (settings.SCRAPER_PODCAST_RSS_DEFAULT). If unset, falls back to NPR's
    Planet Money as a public smoke-test target.
    """
    from django.conf import settings
    feed = getattr(settings, 'SCRAPER_PODCAST_RSS_DEFAULT', '') or DEFAULT_FEED
    logger.info('Resolving podcast RSS: %s', feed)
    return resolve_podcast_rss(feed, limit=limit)