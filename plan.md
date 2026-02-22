# Video Editor API — Implementation Plan

## Overview

A stateless Python/FastAPI microservice for an n8n content pipeline. Handles three heavy video operations: AI-driven face-tracking crop (YOLOv8), FFmpeg subtitle burn-in, and image-to-video slideshow stitching (Ken Burns + crossfade).

**Pattern:** Mirrors the sibling `veo-auto` service — Google Drive credentials + file IDs come in the request body; Google Drive shareable URLs (`https://drive.google.com/file/d/ID/view`) are returned via webhook callback.

**Async lifecycle:** Every endpoint returns `202 Accepted` immediately and posts the result to `webhook_callback` when done.

---

## Project Structure

```
video-editor-api/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, router registration, /health
│   ├── models/
│   │   ├── __init__.py
│   │   ├── common.py              # Shared credential + AcceptedResponse models
│   │   ├── generate_clips.py      # Request/webhook models for /generate-clips
│   │   └── ffmpeg_compose.py      # Request/webhook models for /ffmpeg-compose (both tasks)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── gdrive.py              # Drive client factory, validate, download, upload
│   │   ├── cutter.py              # YOLOv8 face track + Savitzky-Golay + FFmpeg crop
│   │   ├── finisher.py            # FFmpeg SRT→ASS + style patch + burn-in
│   │   └── stitcher.py            # FFmpeg Ken Burns + crossfade image-to-video
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── generate_clips.py      # POST /api/v1/generate-clips
│   │   └── ffmpeg_compose.py      # POST /api/v1/ffmpeg-compose (dispatches by task)
│   └── utils/
│       ├── __init__.py
│       ├── webhook.py             # POST to webhook_callback (3 retries, exponential backoff)
│       └── job_dir.py             # /tmp/job_<uuid>/ context manager (guaranteed cleanup)
├── weights/
│   └── yolov8n-face.pt            # YOLO face detection weights (download separately)
├── requirements.txt
└── .env.example
```

---

## Endpoints

### POST `/api/v1/generate-clips`

Takes a horizontal source video, runs YOLOv8 face tracking + Savitzky-Golay stabilization, and crops into vertical 9:16 clips per provided timestamps.

**Request:**
```json
{
  "google_drive": {
    "credentials": { "type": "service_account", "project_id": "...", "private_key": "...", "client_email": "..." },
    "source_file_id": "GDRIVE_FILE_ID_OF_SOURCE_VIDEO",
    "target_folder_id": "GDRIVE_FOLDER_ID"
  },
  "timestamps": [
    { "start": 12.5, "end": 45.0 },
    { "start": 60.0, "end": 90.0 }
  ],
  "processing_rules": {
    "aspect_ratio": "9:16",
    "apply_face_tracking": true,
    "stabilization_filter": "savitzky-golay"
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Webhook — success:**
```json
{
  "status": "success",
  "clips": [
    { "drive_url": "https://drive.google.com/file/d/ID1/view", "drive_file_id": "ID1" },
    { "drive_url": "https://drive.google.com/file/d/ID2/view", "drive_file_id": "ID2" }
  ]
}
```

---

### POST `/api/v1/ffmpeg-compose`

A deterministic FFmpeg composition engine. Supports two task types selected by the `task` field.

#### Task: `add_captions`

Burns an `.srt` subtitle file directly onto video frames using a custom ASS style.

**Request:**
```json
{
  "task": "add_captions",
  "google_drive": {
    "credentials": { "type": "service_account", "...": "..." },
    "video_file_id": "GDRIVE_VIDEO_FILE_ID",
    "srt_file_id": "GDRIVE_SRT_FILE_ID",
    "target_folder_id": "GDRIVE_FOLDER_ID"
  },
  "caption_styling": {
    "font": "Montserrat-Black",
    "font_size": 24,
    "primary_color": "&H00FFFF&",
    "alignment": 2,
    "margin_v": 150
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Webhook — success:**
```json
{
  "status": "success",
  "composed_media": { "drive_url": "https://drive.google.com/file/d/ID/view", "drive_file_id": "ID" }
}
```

---

#### Task: `stitch_images`

Takes an array of AI-generated images (from Drive) and an ElevenLabs audio track, stitches them into a single `.mp4` with Ken Burns zoom/pan and crossfade transitions.

**Request:**
```json
{
  "task": "stitch_images",
  "google_drive": {
    "credentials": { "type": "service_account", "...": "..." },
    "image_ids": ["1A2B3C_image_1", "4D5E6F_image_2", "7G8H9I_image_3"],
    "audio_id": "9Z8Y7X_elevenlabs_voiceover",
    "target_folder_id": "GDRIVE_FOLDER_ID"
  },
  "operations": {
    "resolution": "1080x1920",
    "duration_per_image": 4.5,
    "transition": "crossfade",
    "apply_ken_burns": true
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Webhook — success:**
```json
{
  "status": "success",
  "composed_media": { "drive_url": "https://drive.google.com/file/d/ID/view", "drive_file_id": "ID" }
}
```

---

### Webhook — error (all endpoints)
```json
{
  "status": "error",
  "error_message": "FFmpeg failed: [libx264 @ 0x...] width not divisible by 2"
}
```

> Both `service_account` and `oauth2` credential types are supported, auto-detected via the `type` field.

---

## Background Task Lifecycle

Every endpoint follows this exact sequence in a `BackgroundTask`:

```
1. ISOLATE  — create /tmp/job_<uuid>/ directory
2. VALIDATE — Google Drive credentials + target folder access check
3. INGEST   — download source assets from Drive into job directory
4. PROCESS  — run the appropriate engine (cutter / finisher / stitcher)
5. EGRESS   — upload output(s) to target_folder_id, get drive_url + drive_file_id
6. NOTIFY   — POST result payload to webhook_callback
7. SANITIZE — shutil.rmtree(job_dir) — always runs, even on error
```

Error path: exception is caught → step 7 runs → error payload POSTed to webhook.

---

## Service Implementations

### `gdrive.py` — Google Drive layer (mirrors `veo-auto/src/gdrive.ts`)

| Function | Description |
|---|---|
| `create_drive_client(credentials)` | Builds a Drive v3 client from `service_account` or `oauth2` credentials |
| `validate_google_drive(credentials, folder_id)` | Verifies credentials + folder access before any I/O |
| `download_from_google_drive(credentials, file_id, dest_path)` | Downloads a Drive file using `MediaIoBaseDownload` (32MB chunks) |
| `upload_to_google_drive(local_path, credentials, target_folder_id)` | Resumable upload, sets `reader/anyone` permission, returns `(drive_url, drive_file_id)` |

### `cutter.py` — Face-tracking crop engine

Per timestamp segment:
1. FFmpeg stream-copy segment extraction (no re-encode, fast)
2. OpenCV `VideoCapture` + YOLOv8 face detection per frame
3. Fallback to previous center on missed detection
4. Savitzky-Golay smoothing on center-x/y timeseries (`scipy.signal.savgol_filter`)
5. Clamp crop window to video bounds
6. Write FFmpeg `sendcmd` file with per-frame `crop x/y` values
7. Single FFmpeg encode pass: `sendcmd → crop → scale → libx264/aac`

- `apply_face_tracking: false` → falls back to static center-crop (no YOLO)
- YOLO model loaded once per process as a singleton (weights: `./weights/yolov8n-face.pt`)

### `finisher.py` — Caption burn-in engine

1. FFmpeg built-in SRT → ASS format conversion
2. Regex-replace `Style: Default` line with custom `CaptionStyling` values
3. FFmpeg `vf=ass=<file>` burn-in → `libx264 crf=18`, `aac 192k`

### `stitcher.py` — Image-to-video engine

1. Download all images + audio from Drive
2. Per image: render Ken Burns clip via FFmpeg `zoompan` filter (zoom 1.0→1.5, with per-image pan variation)
3. Chain clips with `xfade=transition=fade:duration=0.5` between each pair
4. Mux in audio track (`-shortest` to trim to the shorter of video/audio)
5. Final encode: `libx264 crf=20 preset=fast`, `aac 192k`

- `apply_ken_burns: false` → static image loop (no zoompan)
- `transition: "crossfade"` → `xfade=transition=fade`

---

## Data Models (Pydantic v2)

```
common.py
  ServiceAccountCredentials   (type: "service_account", extra fields allowed)
  OAuth2Credentials           (type: "oauth2", client_id + client_secret + refresh_token)
  GoogleDriveCredentials      Annotated union discriminated by "type"
  AcceptedResponse            { status: "accepted", message: str }

generate_clips.py
  GenerateClipsDriveConfig    credentials + source_file_id + target_folder_id
  Timestamp                   { start: float, end: float }
  ProcessingRules             aspect_ratio, apply_face_tracking, stabilization_filter
  GenerateClipsRequest        google_drive + timestamps + processing_rules + webhook_callback
  ClipResult                  { drive_url, drive_file_id }
  GenerateClipsSuccessPayload { status: "success", clips: List[ClipResult] }
  ErrorPayload                { status: "error", error_message: str }

ffmpeg_compose.py
  AddCaptionsDriveConfig      credentials + video_file_id + srt_file_id + target_folder_id
  CaptionStyling              font, font_size, primary_color, alignment, margin_v
  AddCaptionsRequest          task: "add_captions" + google_drive + caption_styling + webhook_callback

  StitchImagesDriveConfig     credentials + image_ids + audio_id + target_folder_id
  StitchOperations            resolution, duration_per_image, transition, apply_ken_burns
  StitchImagesRequest         task: "stitch_images" + google_drive + operations + webhook_callback

  FFmpegComposeRequest        Annotated[Union[AddCaptionsRequest, StitchImagesRequest], discriminator="task"]
  ComposedMediaResult         { drive_url, drive_file_id }
  FFmpegComposeSuccessPayload { status: "success", composed_media: ComposedMediaResult }
  ErrorPayload                { status: "error", error_message: str }
```

---

## Dependencies (`requirements.txt`)

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.8.2
google-api-python-client==2.143.0
google-auth==2.34.0
google-auth-httplib2==0.2.0
ultralytics==8.2.90
opencv-python-headless==4.10.0.84
ffmpeg-python==0.2.0
scipy==1.14.1
numpy==1.26.4
requests==2.32.3
```

**System requirement:** `ffmpeg` must be installed on the host (`apt install ffmpeg` / `brew install ffmpeg`).

---

## Running the Service

```bash
# Install Python dependencies
pip install -r requirements.txt

# Download YOLO face weights
mkdir -p weights
# Place yolov8n-face.pt at ./weights/yolov8n-face.pt
# (download from: https://github.com/akanametov/yolov8-face/releases)

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

**Environment variables (`.env.example`):**
```
YOLO_WEIGHTS=./weights/yolov8n-face.pt
```

---

## Files to Create

| # | File | Purpose |
|---|------|---------|
| 1 | `app/__init__.py` | Package marker |
| 2 | `app/main.py` | FastAPI app factory, router registration, `/health` |
| 3 | `app/models/__init__.py` | Package marker |
| 4 | `app/models/common.py` | Shared credential models |
| 5 | `app/models/generate_clips.py` | Clip-cutting request/webhook models |
| 6 | `app/models/ffmpeg_compose.py` | Compose request/webhook models (both tasks) |
| 7 | `app/services/__init__.py` | Package marker |
| 8 | `app/services/gdrive.py` | Google Drive service layer |
| 9 | `app/services/cutter.py` | YOLOv8 face-tracking crop |
| 10 | `app/services/finisher.py` | Caption burn-in |
| 11 | `app/services/stitcher.py` | Image slideshow with Ken Burns |
| 12 | `app/routers/__init__.py` | Package marker |
| 13 | `app/routers/generate_clips.py` | `/api/v1/generate-clips` endpoint |
| 14 | `app/routers/ffmpeg_compose.py` | `/api/v1/ffmpeg-compose` endpoint |
| 15 | `app/utils/__init__.py` | Package marker |
| 16 | `app/utils/job_dir.py` | `/tmp/job_<uuid>/` context manager |
| 17 | `app/utils/webhook.py` | Webhook POST with retry |
| 18 | `requirements.txt` | Python dependencies |
| 19 | `.env.example` | Environment variable template |

---

## Verification

```bash
# 1. Health check
curl http://localhost:8000/health
# → {"ok": true}

# 2. Test add_captions
curl -X POST http://localhost:8000/api/v1/ffmpeg-compose \
  -H "Content-Type: application/json" \
  -d '{ "task": "add_captions", "google_drive": { ... }, "caption_styling": { ... }, "webhook_callback": "https://requestbin.io/..." }'
# → 202 Accepted; check requestbin for webhook with drive_url

# 3. Test stitch_images
curl -X POST http://localhost:8000/api/v1/ffmpeg-compose \
  -H "Content-Type: application/json" \
  -d '{ "task": "stitch_images", "google_drive": { ... }, "operations": { ... }, "webhook_callback": "https://requestbin.io/..." }'
# → 202 Accepted; check requestbin for webhook with drive_url

# 4. Test generate-clips
curl -X POST http://localhost:8000/api/v1/generate-clips \
  -H "Content-Type: application/json" \
  -d '{ "google_drive": { ... }, "timestamps": [...], "processing_rules": { ... }, "webhook_callback": "https://requestbin.io/..." }'
# → 202 Accepted; check requestbin for webhook with clips array of drive_urls
```
