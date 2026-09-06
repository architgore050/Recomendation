import hashlib
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 1. Use Regex for Word Boundary Matching to prevent false positives
_BLOCKED_PHRASES = [
    "hate speech",
    "csam",
    "child sexual",
    "obscenity",
    "terrorism",
    "extremist",
    "violence",
]
# Pre-compile the regex pattern for fast execution across workers
_BLOCKED_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(p) for p in _BLOCKED_PHRASES) + r')\b', re.IGNORECASE)

# Note: In a multi-worker Celery architecture, this set must be populated 
# strictly via code commits before boot. Runtime modifications will not sync.
_FINGERPRINT_BLOCKLIST: set[str] = {
    # "a1b2c3d4..."
}

def check_transcript_for_prohibited_content(transcript_text: Optional[str]) -> Tuple[bool, Optional[str]]:
    if not transcript_text:
        return True, None
    
    match = _BLOCKED_PATTERN.search(transcript_text)
    if match:
        reason = f"Blocked phrase detected: '{match.group(1)}' (category: prohibited content)"
        logger.warning("Moderation rejected transcript: %s", reason)
        return False, reason
        
    return True, None

def check_tags_for_prohibited_content(tags: Optional[list]) -> Tuple[bool, Optional[str]]:
    if not tags:
        return True, None
        
    for tag in tags:
        match = _BLOCKED_PATTERN.search(str(tag))
        if match:
            reason = f"Blocked phrase detected in tag '{tag}': '{match.group(1)}'"
            logger.warning("Moderation rejected tag: %s", reason)
            return False, reason
            
    return True, None

def compute_audio_fingerprint(django_file) -> str:
    """
    Computes SHA256 abstractly via Django's File API. 
    This works universally for local disks and remote MinIO/S3 buckets.
    """
    h = hashlib.sha256()
    try:
        # Open the file via the storage backend (streams from S3 if necessary)
        django_file.open("rb")
        # .chunks() prevents loading massive files entirely into RAM
        for chunk in django_file.chunks(chunk_size=8192):
            h.update(chunk)
    except Exception as exc:
        logger.error("Fingerprint computation failed: %s", exc)
        return ""
    finally:
        django_file.close()
        
    return h.hexdigest()

def check_fingerprint_blocklist(fingerprint: str) -> Tuple[bool, Optional[str]]:
    if not fingerprint:
        return False, "Fingerprint computation failed (empty hash)"
        
    if fingerprint in _FINGERPRINT_BLOCKLIST:
        reason = f"Audio fingerprint blocked: {fingerprint}"
        logger.warning("Moderation rejected fingerprint: %s", reason)
        return False, reason
        
    return True, None

def run_moderation_check(clip_id) -> Tuple[bool, Optional[str]]:
    """
    Runs full moderation check.
    Consolidates the DB save to prevent multiple writes.
    """
    from ..models import AudioClip
    
    try:
        clip = AudioClip.objects.get(id=clip_id)
    except AudioClip.DoesNotExist:
        return False, f"Clip {clip_id} not found"

    approved = True
    reason = None

    # 1. Fingerprint check (Using the abstract File object)
    if clip.original_file:
        fingerprint = compute_audio_fingerprint(clip.original_file)
        approved, reason = check_fingerprint_blocklist(fingerprint)
        
    # 2. Tags check (Only run if previous checks passed)
    if approved:
        approved, reason = check_tags_for_prohibited_content(clip.tags)

    # 3. Transcript check
    if approved:
        transcript_text = getattr(clip, "transcript_text", None)
        approved, reason = check_transcript_for_prohibited_content(transcript_text)

    # Single DB update transaction
    clip.moderation_approved = approved
    clip.save(update_fields=["moderation_approved"])
    
    return approved, reason

'''
"""Content moderation pipeline for EchoFlow India regulatory readiness.



ISSUE-04 (Critical): Adds transcript-based and fingerprint-based moderation

checks for user-uploaded audio clips. ISSUE-05 (copyright acknowledgment)

relies on the serializer enforcing acknowledgment before DB persistence.



DECISION: v1 uses sha256 fingerprint of the normalized file path and a

hard-coded blocked-phrase list for transcript text. This avoids external

API dependencies (AWS Rekognition, Google Vision, external moderation

services) and works fully offline inside the Docker container.



SECURITY: Blocked-phrase checks run against lowercase transcript text

and against tags (AI keywords). The fingerprint check uses sha256 of the

normalized audio file — sufficient for v1 per audit doc.



HACK: The fingerprint blocklist is a module-level set (not a DB table)

for v1. A production deployment should move this to Redis / DB.



TODO: Replace blocked-phrase list with a multilingual India-specific

prohibited-content database (IT Rules 2021 categories: hate speech,

CSAM descriptions, obscene terms, terrorism, etc.).

"""

import hashlib

import logging

from typing import Optional, Tuple



logger = logging.getLogger(__name__)



# Blocked phrases mapped to India regulatory categories per IT Rules 2021.

# This is a minimal v1 list. A production system requires a larger,

# multilingual database.

_BLOCKED_PHRASES = [

"hate speech",

"csam",

"child sexual",

"obscenity",

"terrorism",

"extremist",

"violence",

# Add India-specific categories as needed

]



# Fingerprint blocklist (sha256 hex). v1: empty — populated at deploy time.

# DECISION: Using an in-memory set rather than DB/Redis for minimal v1.

_FINGERPRINT_BLOCKLIST: set[str] = set()





def _normalize_text(text: Optional[str]) -> str:

if not text:

return ""

return text.lower()





def check_transcript_for_prohibited_content(transcript_text: Optional[str]) -> Tuple[bool, Optional[str]]:

"""Compare transcript_text against blocked-phrase list.



Returns:

(True, None) if approved (no blocked content found)

(False, reason_str) if rejected and reason for audit log.

"""

normalized = _normalize_text(transcript_text)

for phrase in _BLOCKED_PHRASES:

# Simple substring match for v1. Production requires token-level

# or classifier-based matching.

if phrase in normalized:

reason = f"Blocked phrase detected: '{phrase}' (category: prohibited content)"

logger.warning("Moderation rejected transcript: %s", reason)

return False, reason

return True, None





def check_tags_for_prohibited_content(tags: Optional[list]) -> Tuple[bool, Optional[str]]:

"""Compare AI-extracted tags against blocked-phrase list.



Returns the same (bool, Optional[str]) contract as transcript check.

"""

if not tags:

return True, None

for tag in tags:

tag_str = str(tag).lower()

for phrase in _BLOCKED_PHRASES:

if phrase in tag_str:

reason = f"Blocked phrase detected in tag '{tag}': '{phrase}'"

logger.warning("Moderation rejected tag: %s", reason)

return False, reason

return True, None





def compute_audio_fingerprint(path: str) -> str:

"""Compute sha256 fingerprint of the file at `path`.



DECISION: sha256 of normalized_path content for v1. Per audit doc,

this is sufficient for v1 fingerprint blocklist checks.

"""

h = hashlib.sha256()

try:

with open(path, "rb") as f:

for chunk in iter(lambda: f.read(8192), b""):

h.update(chunk)

except FileNotFoundError:

logger.error("Fingerprint computation failed: file not found: %s", path)

return ""

return h.hexdigest()





def check_fingerprint_blocklist(fingerprint: str) -> Tuple[bool, Optional[str]]:

"""Compare fingerprint against blocklist.



Returns:

(True, None) if approved (not blocked)

(False, reason_str) if blocked

"""

if not fingerprint:

# Empty fingerprint means file missing — treat as failure for

# moderation pipeline, but not a blocklisted match.

return False, "Fingerprint computation failed (empty hash)"

if fingerprint in _FINGERPRINT_BLOCKLIST:

reason = f"Audio fingerprint blocked: {fingerprint}"

logger.warning("Moderation rejected fingerprint: %s", reason)

return False, reason

return True, None





def run_moderation_check(clip_id) -> Tuple[bool, Optional[str]]:

"""Run full moderation check for an AudioClip.



Loads the clip, checks transcript (if transcript_text exists), tags,

and audio fingerprint against blocklists. Updates clip.moderation_approved.



Returns (approved_bool, reason_or_none).

"""

from ..models import AudioClip

try:

clip = AudioClip.objects.get(id=clip_id)

except AudioClip.DoesNotExist:

return False, f"Clip {clip_id} not found"



# 1. Fingerprint check on original_file (if present locally)

fingerprint_approved = True

fingerprint_reason = None

if clip.original_file:

try:

fingerprint = compute_audio_fingerprint(clip.original_file.path)

except Exception:

try:

storage_path = clip.original_file.storage.path(clip.original_file.name)

fingerprint = compute_audio_fingerprint(storage_path)

except Exception as exc:

logger.warning("Fingerprint computation skipped for clip %s: %s", clip_id, exc)

fingerprint = ""

fingerprint_approved, fingerprint_reason = check_fingerprint_blocklist(fingerprint)

if not fingerprint_approved:

clip.moderation_approved = False

clip.save(update_fields=["moderation_approved"])

return False, fingerprint_reason



# 2. Tags moderation (AI keywords from KeyBERT / Whisper pipeline)

tags_approved, tags_reason = check_tags_for_prohibited_content(clip.tags)

if not tags_approved:

clip.moderation_approved = False

clip.save(update_fields=["moderation_approved"])

return False, tags_reason



# 3. Transcript check (if transcript_text exists; in v1 this is

# stored separately. The task process_audio_to_hls should set it

# or we can read from clip if added later.)

# HACK: The AudioClip model currently does not have transcript_text.

# We attempt to read it; if missing, we skip.

transcript_text = getattr(clip, "transcript_text", None)

if transcript_text is not None:

transcript_approved, transcript_reason = check_transcript_for_prohibited_content(transcript_text)

if not transcript_approved:

clip.moderation_approved = False

clip.save(update_fields=["moderation_approved"])

return False, transcript_reason



# All checks passed — approve

clip.moderation_approved = True

clip.save(update_fields=["moderation_approved"])

return True, None 
'''