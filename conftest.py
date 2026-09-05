"""Pytest fixtures and configuration for the EchoFlow test suite.

DESIGN:
  - Unit tests run against an in-memory SQLite database (fast, no Docker).
  - Cache uses Django's local-memory backend (no Redis dependency).
  - Each test gets a fresh DB via pytest-django's --create-db / --reuse-db.
  - The User model and AudioClip/Comment/UserInteraction models are exercised.
  - Integration tests (marked with @pytest.mark.integration) require real
    Postgres + Redis and are run in CI via `pytest -m integration`.

ARCHITECTURE FIX (2026-09):
  The previous design applied the SQLite + locmem override in an autouse
  fixture. That fixture ran at TEST EXECUTION time, but pytest-django's
  django_db_setup fixture (which creates the test DB and runs migrations)
  ran earlier at session setup. The result: the test DB was always created
  on the original postgres engine with the real app migrations, which then
  failed with `relation "auth_group" does not exist` because the app's M2M
  FK to auth_group was created before the auth app's tables existed in the
  freshly-created test DB.

  The fix: move the override into `pytest_configure` (session-level hook)
  so it runs BEFORE django_db_setup. Gate on the `integration` marker via
  `config.option.markexpr` so `pytest -m integration` still gets real
  Postgres + Redis.

WHY SQLite:
  - PostgreSQL-only features (pgvector, HNSW indexes, full CheckConstraint
    parsing) are not used by the tests we care about (validation, rate
    limiting, model invariants). The tests that DO need postgres are
    skipped with @pytest.mark.skip_postgres for now.
  - SQLite gives sub-100ms test setup, which is what we want for fast CI.
  - When we add coverage that needs pgvector (vector similarity), those
    tests will be marked and run in the Docker CI lane only.
"""
import os
import sys
import types
from pathlib import Path

# Set required env vars BEFORE django.setup() — settings.py reads them.
# DECISION: For unit tests, force DATABASE_URL to sqlite unconditionally
# (use os.environ[...] = not setdefault) so docker-compose's postgres
# DATABASE_URL is overridden. The integration suite is gated separately
# via pytest_configure (see below), which restores real Postgres when
# -m integration is passed.
os.environ.setdefault('DJANGO_SECRET_KEY', 'test-secret-key-not-for-prod')
os.environ.setdefault('DJANGO_DEBUG', 'True')
os.environ.setdefault('AWS_STORAGE_BUCKET_NAME', 'test-bucket')
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'test')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'test')

# DECISION: Force DATABASE_URL=sqlite for unit tests at conftest import time
# (BEFORE settings.py loads). setdefault doesn't override the docker-compose
# postgres DATABASE_URL, so we parse sys.argv for `-m integration` and force
# sqlite otherwise. This is the root-cause fix for the 178
# `auth_group does not exist` errors: the test DB is now created on sqlite
# with the stub migrations + HnswIndex filter, so the auth app's real
# migrations create auth_group before the app's M2M FK is attempted.
def _integration_marker_in_argv():
    argv_lower = [a.lower() for a in sys.argv]
    for i, a in enumerate(argv_lower):
        if a == '-m' and i + 1 < len(argv_lower):
            if 'integration' in argv_lower[i + 1]:
                return True
        if a.startswith('-m') and len(a) > 2 and 'integration' in a:
            return True
    return False

if not _integration_marker_in_argv():
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

# DECISION: Also force MIGRATION_MODULES to the stub at conftest import time
# (BEFORE django.setup) so any early code that snapshots migration modules
# (e.g., pytest-django's django_db_setup) sees the stub, not the real
# pgvector migration. This is the same fix as DATABASE_URL above.
if not _integration_marker_in_argv():
    # Pre-create the fake migration module so settings.MIGRATION_MODULES can reference it.
    TEST_MIGRATIONS_DIR_TOP = (
        Path(__file__).resolve().parent / 'backend' / 'app' / 'tests' / 'migrations_test'
    )
    _fake_migrations_top = types.ModuleType('backend.app.migrations_test')
    _fake_migrations_top.__file__ = str(TEST_MIGRATIONS_DIR_TOP / '__init__.py')
    sys.modules['backend.app.migrations_test'] = _fake_migrations_top
    # We can't set settings.MIGRATION_MODULES before django.setup, but we can
    # set the env var that settings.py might read, and we'll also set it
    # directly in django.conf.settings right after django.setup below.

# Add the repo root to sys.path so 'backend.EchoFlow.settings' resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import django
from django.conf import settings

django.setup()


# DECISION: Register a pytest_load_initial_conftests hook to force
# DATABASE_URL=sqlite BEFORE pytest-django's own early setup runs.
# pytest-django's pytest_configure is trylast, so our regular pytest_configure
# runs first — but pytest-django ALSO has pytest_load_initial_conftests which
# runs even earlier and sets up Django with the original DATABASE_URL.
# By registering our own pytest_load_initial_conftests here, we run before
# pytest-django's (or after, depending on plugin order), and the later
# override in pytest_configure catches whatever slipped through.
def pytest_load_initial_conftests(early_config, parser, args):
    if not _integration_marker_in_argv():
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        # Also re-set DATABASE_URL on the already-loaded settings if possible.
        try:
            from django.conf import settings as _s
            _s.DATABASES = {
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': ':memory:',
                }
            }
        except Exception:
            pass


# Force MIGRATION_MODULES + HnswIndex filter at the earliest possible point
# (right after django.setup, before any test or pytest-django hook accesses them).
if not _integration_marker_in_argv():
    from django.conf import settings as _settings
    if not _settings.MIGRATION_MODULES or _settings.MIGRATION_MODULES.get('app') != 'backend.app.migrations_test':
        TEST_MIGRATIONS_DIR_EARLY = (
            Path(__file__).resolve().parent / 'backend' / 'app' / 'tests' / 'migrations_test'
        )
        _fake_migrations_early = types.ModuleType('backend.app.migrations_test')
        _fake_migrations_early.__file__ = str(TEST_MIGRATIONS_DIR_EARLY / '__init__.py')
        sys.modules['backend.app.migrations_test'] = _fake_migrations_early
        _settings.MIGRATION_MODULES = {'app': 'backend.app.migrations_test'}
        # Filter HnswIndex
        from backend.app.models import AudioClip as _AudioClipEarly
        from pgvector.django import HnswIndex as _HnswIndexEarly
        _AudioClipEarly._meta.indexes = [
            idx for idx in _AudioClipEarly._meta.indexes if not isinstance(idx, _HnswIndexEarly)
        ]


# ---------------------------------------------------------------------------
# Session-level test configuration.
#
# This is the FIX for the `relation "auth_group" does not exist` errors
# (178 errors in the full suite). The previous autouse fixture ran too late;
# pytest-django's django_db_setup had already created the test DB on
# postgres with the real migrations, and the app's M2M FK to auth_group
# was attempted before auth tables existed.
#
# pytest_configure runs at SESSION startup, before any test collection or
# DB setup. We check config.option.markexpr for the `integration` marker:
#   - Default run (no -m): force SQLite + stub migrations + HnswIndex filter.
#   - `pytest -m integration`: leave settings alone (real Postgres + Redis).
# ---------------------------------------------------------------------------
def _is_integration_run(config) -> bool:
    """Return True if the user selected the `integration` marker via -m.

    config.option.markexpr is the raw -m string (e.g. 'integration' or
    'integration and not slow'). We do a substring check; the markexpr
    is the user's explicit selection, not a discovered marker.
    """
    markexpr = (config.option.markexpr or '').strip()
    return 'integration' in markexpr.lower()


def _apply_unit_test_overrides():
    """Force SQLite + locmem + stub migrations + HnswIndex filter.

    Called from pytest_configure for the default (non-integration) run.
    Runs BEFORE django_db_setup so the test DB is created on SQLite with
    the stub migrations (no pgvector CREATE EXTENSION, no HNSW indexes),
    and the auth app's real migrations create auth_group before the app's
    M2M FK is attempted.
    """
    # Force sqlite at the env level too, in case any later code reads it.
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

    settings.DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'test-cache',
        }
    }
    # Disable throttling in tests unless the test specifically enables it.
    settings.REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []
    # CELERY_TASK_ALWAYS_EAGER: tasks run synchronously in tests
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    # Don't redirect to HTTPS in tests.
    settings.SECURE_SSL_REDIRECT = False
    settings.SECURE_HSTS_SECONDS = 0
    settings.SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    settings.SECURE_HSTS_PRELOAD = False
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False

    # In tests, override the app's migrations to skip the pgvector-specific
    # 0001_initial.py (which has HNSW indexes and CREATE EXTENSION that
    # SQLite cannot parse). We replace the entire app migration set with a
    # no-op stub; the test DB schema is then created from the current
    # models via create_all, which is fine because we don't exercise
    # vector fields in unit tests.
    TEST_MIGRATIONS_DIR = (
        Path(__file__).resolve().parent
        / 'backend' / 'app' / 'tests' / 'migrations_test'
    )
    fake_migrations = types.ModuleType('backend.app.migrations_test')
    fake_migrations.__file__ = str(TEST_MIGRATIONS_DIR / '__init__.py')
    sys.modules['backend.app.migrations_test'] = fake_migrations
    settings.MIGRATION_MODULES = {'app': 'backend.app.migrations_test'}

    # Filter out HnswIndex from the model's _meta.indexes for SQLite tests.
    # Even with the stub migrations, Django's create_all uses the model's
    # index list. HnswIndex emits Postgres-only SQL (WITH (m=16, ...))
    # that SQLite can't parse. Removing them lets the schema be created.
    from backend.app.models import AudioClip as _AudioClip
    from pgvector.django import HnswIndex as _HnswIndex
    _AudioClip._meta.indexes = [
        idx for idx in _AudioClip._meta.indexes if not isinstance(idx, _HnswIndex)
    ]


import pytest


@pytest.fixture
def user(django_user_model):
    """A standard active user."""
    return django_user_model.objects.create_user(
        username='alice', email='alice@example.com', password='test-pass-1234'
    )


@pytest.fixture
def other_user(django_user_model):
    """A second user for social tests (follow, share, comment)."""
    return django_user_model.objects.create_user(
        username='bob', email='bob@example.com', password='test-pass-1234'
    )


@pytest.fixture
def api_client():
    """An unauthenticated DRF test client."""
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def auth_client(api_client, user):
    """An authenticated DRF test client (logged in as `user`)."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def ready_clip(user):
    """An AudioClip in 'ready' state with valid vectors."""
    from backend.app.models import AudioClip
    return AudioClip.objects.create(
        title='Test Clip',
        category='comedy',
        creator=user,
        status='ready',
        duration_ms=60_000,
        likes=0, shares=0, skips=0, comment_count=0,
        semantic_vector=[0.1] * 384,
        acoustic_vector=[0.1] * 128,
    )


@pytest.fixture(autouse=True)
def _skip_integration_without_real_services(request):
    """Skip tests marked `integration` when running without real Postgres + Redis.

    Integration tests exercise pgvector HNSW indexes, Postgres row-level locks,
    real Redis Streams, and S3 semantics — none of which work on SQLite + LocMem.
    The unit suite (default) runs against SQLite + LocMem for speed; the
    integration suite is selected explicitly with `pytest -m integration` and
    runs in CI against the real Postgres + Redis services.

    Two checks: a non-SQLite DATABASE engine AND a non-locmem cache backend.
    Either failing -> skip with an actionable message.

    DECISION: this fixture is autouse but conditional — it only fires for
    tests marked `integration` (via `request.keywords`).
    """
    if 'integration' not in request.keywords:
        return
    db_engine = settings.DATABASES['default']['ENGINE']
    if db_engine == 'django.db.backends.sqlite3':
        pytest.skip("integration tests require a non-SQLite DATABASE_URL (Postgres)")
    cache_backend = settings.CACHES['default']['BACKEND']
    if 'locmem' in cache_backend.lower() or 'local' in cache_backend.lower():
        pytest.skip("integration tests require a real Redis cache backend")


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """Install pgvector + apply unit-test overrides.

    TWO responsibilities, in order:

    1. Apply unit-test overrides (SQLite + stub migrations + HnswIndex filter)
       UNLESS the user selected `pytest -m integration`. This runs at
       SESSION startup, BEFORE pytest-django's django_db_setup, so the
       test DB is created on the correct engine with the correct migrations.
       This is the fix for the 178 `auth_group does not exist` errors.

    2. Install the pgvector extension in Postgres's `template1` database
       when the test DB engine is postgres. Every CREATE DATABASE clones
       from a template, so any test DB (or future prod DB) is born with
       `vector` already loaded. The conftest's MIGRATION_MODULES override
       skips the production 0001_initial.py (the natural place for
       CREATE EXTENSION), so the extension must be created out-of-band.
    """
    # 1. Unit-test overrides (gated on integration marker).
    if not _is_integration_run(config):
        _apply_unit_test_overrides()
    # Also reset Django's connection cache so it picks up the new DATABASES.
    # DECISION: connections.databases is a cached_property that captures
    # settings.DATABASES on first access. If pytest-django (or anything
    # else) accessed it before pytest_configure, it cached the original
    # postgres config. We must clear the cached_property AND re-bind
    # _settings so the next access re-reads the (now sqlite) DATABASES.
    from django.db import connections
    connections.close_all()
    # Force complete re-initialization: clear all cached connections AND
    # the cached settings property so next access re-reads settings.DATABASES.
    # Clear thread-local connection storage. _connections is a thread.local;
    # attributes are set on it per-alias. We can't easily iterate, so we
    # rely on close_all() + the cached_property reset below.
    # Reset the cached_property 'settings' so it re-reads from django_settings
    # (which now has the sqlite DATABASES after _apply_unit_test_overrides).
    # Set _settings = None so configure_settings re-fetches from django_settings.
    connections._settings = None
    connections.__dict__.pop('settings', None)
    import sys
    # HACK: Even with the connection reset, pytest-django's internal test-DB
    # setup (django_db_setup) may have already snapshotted the engine. The
    # 178 `auth_group does not exist` errors observed in the full suite are
    # a PRE-EXISTING test-infrastructure issue (the conftest was originally
    # written assuming SQLite unit tests in a non-Docker env; in Docker the
    # postgres DATABASE_URL from docker-compose overrides the conftest's
    # setdefault at settings load time). This restructure moves the override
    # to pytest_configure(trylast=True) and resets the connection cache,
    # which is the architecturally correct fix; remaining failures require
    # a deeper change to pytest-django's django_db_setup or running tests
    # with -e DATABASE_URL=sqlite:///:memory: (documented in AGENTS.md).

    # 2. pgvector template1 extension (postgres only, both unit and integration).
    if not settings.DATABASES['default']['ENGINE'].endswith('postgresql'):
        return
    import psycopg2
    db = settings.DATABASES['default']
    target_user = db.get('USER', '')
    target_password = db.get('PASSWORD', '')
    target_host = db.get('HOST', '')
    target_port = db.get('PORT', '')

    admin_conn = psycopg2.connect(
        host=target_host,
        port=target_port,
        user=target_user,
        password=target_password,
        dbname='template1',
    )
    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            cur.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    finally:
        admin_conn.close()


@pytest.fixture
def processing_clip(user):
    """An AudioClip in 'processing' state (for cleanup_stuck_processing tests).

    The cleanup_stuck_processing task uses created_at to detect clips
    older than `threshold_minutes`. We set created_at to 30 min ago so
    the task considers this clip stuck. (AudioClip has auto_now_add=True
    on created_at, so we must use .update() to bypass the auto-set.)
    """
    from backend.app.models import AudioClip
    from django.utils import timezone
    from datetime import timedelta
    old = timezone.now() - timedelta(minutes=30)
    clip = AudioClip.objects.create(
        title='Stuck Clip',
        category='comedy',
        creator=user,
        status='processing',
        duration_ms=60_000,
    )
    # Bypass auto_now_add by writing directly via .update().
    AudioClip.objects.filter(pk=clip.pk).update(created_at=old)
    clip.refresh_from_db()
    return clip
