# Backend-owned upload storage

## Changes Needed

- Browser uploads must call the Django `/clips/` endpoint instead of the
  frontend demo server.
- Both web and mobile clients must send the backend field name
  `original_file`.
- Upload requests must include the backend-required
  `copyright_acknowledgement` field.
- Django must allow the local web origins used by the two clients.
- The frontend demo server must not write user media to `frontend/uploads`.

## How Changes Will Be Made

The web API client will use `VITE_API_BASE_URL`, defaulting to the local Django
endpoint at `http://localhost:8005`. Existing relative API paths will be
resolved against that base URL. Mobile will continue using its platform-aware
`EXPO_PUBLIC_API_BASE_URL`, with Expo web pointing to Django rather than the
mock server.

The Django `AudioUploadSerializer` remains the authority for validation and
storage. Its `FileField` will save through the configured S3-compatible
`STORAGES["default"]` backend. The local mock server will use in-memory
multipart handling only for non-production demo routes and will not expose a
durable local upload directory.

## Why This and Not Anything Else

The backend already centralizes object-storage configuration and Celery/HLS
processing. Duplicating upload persistence in the frontend server creates a
second storage system that workers do not consume and can leave media stranded
on the UI host. Direct client-to-Django upload preserves authentication,
validation, moderation, and object-storage ownership in one boundary.

## Files Affected

- `frontend/src/api/client.ts`
- `frontend/src/pages/Upload.tsx`
- `frontend/server.ts`
- `mobile/src/services/api.ts`
- `mobile/src/screens/UploadScreen.tsx`
- `backend/EchoFlow/settings.py`

## Architecture & Data Flow

1. Web or mobile client creates multipart form data.
2. Client sends `POST /clips/` to Django with its access token.
3. Django validates the file and metadata.
4. Django saves `original_file` through S3-compatible storage.
5. Django returns `202` with the clip ID and processing status.
6. Celery workers read the stored object, create HLS derivatives, and write
   derivatives back to object storage.
7. Feed serializers return signed playback URLs.

## Test Cases

- Web upload request targets `http://localhost:8005/clips/` by default.
- Mobile upload uses `original_file`, not `audio_file`.
- Upload includes `copyright_acknowledgement=true`.
- Django responds with CORS headers for `http://localhost:3001` and
  `http://localhost:8081`.
- No upload code creates or writes `frontend/uploads`.
- Web build, mobile export, and targeted TypeScript checks pass.

## Edge Cases

- A missing Django backend or object-storage environment must surface as an
  upload error; the client must not silently fall back to local disk.
- Direct browser uploads require valid Django access tokens.
- The Docker backend must have `AWS_STORAGE_BUCKET_NAME`, access credentials,
  and its configured S3-compatible endpoint before uploads can succeed.
