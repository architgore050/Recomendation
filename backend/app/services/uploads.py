"""Upload service layer.

Stage 2 boundary. The only call here today is `finalize_upload`, which
moves the `transaction.on_commit(process_audio_to_hls.delay(...))` line
out of the view so the view does not own Celery dispatch.

When P1.3 (presigned PUT) lands, this module grows a `get_signed_put_url`
function and the view becomes a thin wrapper.
"""
from __future__ import annotations

from django.db import transaction

from ..models import AudioClip
from ..tasks import process_audio_to_hls
from .task_publisher import publish


def finalize_upload(clip: AudioClip) -> None:
    """Prepare upload for moderation (v1 Option A). HLS processing is
    blocked until moderation_approved is set to True by an operator.

    DECISION: We keep the original row creation (for audit/trail) but
    do NOT enqueue process_audio_to_hls until moderation passes.
    Tradeoff: Prohibited content is stored temporarily in object
    storage but never rendered to users (feed filter blocks it).
    A future Option B (StagingClip) avoids storage of prohibited
    content entirely.
    """
    # Explicitly set moderation_approved=False (model default, but
    # defensive for any existing rows created without it).
    if clip.moderation_approved:
        clip.moderation_approved = False
        clip.save(update_fields=["moderation_approved"])
    # Do NOT enqueue process_audio_to_hls here. The approve-moderation
    # endpoint will enqueue it after moderation passes.
    # HACK: We keep the transaction.on_commit for future extensibility
    # (e.g. audit log write) but don't dispatch the HLS task.
    transaction.on_commit(lambda: None)


def trigger_hls_processing(clip: AudioClip) -> None:
    """Enqueue HLS processing for an approved clip.

    Called by the approve-moderation endpoint after moderation passes.
    """
    # Only process if moderation is approved.
    if not clip.moderation_approved:
        raise ValueError("Cannot trigger HLS processing for unapproved clip.")
    transaction.on_commit(lambda: publish(process_audio_to_hls, str(clip.id)))
