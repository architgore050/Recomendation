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