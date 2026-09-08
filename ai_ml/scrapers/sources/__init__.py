"""Source connectors for the scraper.

Each source module should provide a `fetch_audio(limit)` function that returns
an iterable of dicts with keys: `url`, `title`, `page_url`, and optionally `license` and `id`.

NOTE: The `pixabay` and `podcast_index` connectors are temporarily disabled
(see commented-out lines below). They require API keys (SCRAPER_PIXABAY_API_KEY,
SCRAPER_PODCAST_INDEX_API_KEY, SCRAPER_PODCAST_INDEX_API_SECRET) that are not
currently configured. Uncomment the imports and SOURCES entries once those
keys are available to re-enable the connectors.
"""

from . import (
    wikimedia_commons,
    internet_archive,
    freesound,
    kaggle,
    openverse,
    librivox,
    free_music_archive,
    # pixabay,          # DISABLED: needs SCRAPER_PIXABAY_API_KEY — uncomment once configured
    # podcast_index,    # DISABLED: needs SCRAPER_PODCAST_INDEX_API_KEY + _SECRET — uncomment once configured
    podcast_rss,
    bbc_sound_effects,
    musopen,
    loc_national_jukebox,
    usgov_audio,
    youtube,
    youtube_shorts,
)

SOURCES = {
    'wikimedia': wikimedia_commons,
    'internet_archive': internet_archive,
    'freesound': freesound,
    'kaggle': kaggle,
    'openverse': openverse,
    'librivox': librivox,
    'free_music_archive': free_music_archive,
    # 'pixabay': pixabay,                  # DISABLED — see note above
    # 'podcast_index': podcast_index,      # DISABLED — see note above
    'podcast_rss': podcast_rss,
    'bbc_sound_effects': bbc_sound_effects,
    'musopen': musopen,
    'loc_national_jukebox': loc_national_jukebox,
    'usgov_audio': usgov_audio,
    'youtube': youtube,
    'youtube_shorts': youtube_shorts,
}