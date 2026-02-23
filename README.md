# Video & Audio Processing API

A stateless Python/FastAPI microservice for comprehensive media processing in n8n workflows. Supports video editing (face-tracking crop, subtitle burn-in, slideshow stitching) and audio operations (transcription, voice generation, editing).

## Features

### Video Operations
- **AI Face-Tracking Crop** - Convert horizontal videos to vertical 9:16 clips with YOLOv8 face detection
- **Subtitle Burn-In** - Add styled captions to videos using FFmpeg ASS subtitles
- **Image Slideshow** - Create videos from images with Ken Burns effect and crossfade transitions

### Audio Operations
- **Speech-to-Text** - Transcribe videos/audio to SRT subtitles using faster-whisper
- **Text-to-Speech** - Generate voiceovers with ElevenLabs API
- **Audio Editing** - Trim, merge, and adjust volume of audio files

## Architecture

**Async Lifecycle:** All endpoints return `202 Accepted` immediately and post results to webhook callback when complete.

**Pattern:** Google Drive credentials + file IDs in request body → Processing → Drive shareable URLs returned via webhook.

**Isolation:** Each job runs in isolated `/tmp/job_<uuid>/` directory with guaranteed cleanup.

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg installed (`apt install ffmpeg` or `brew install ffmpeg`)
- Google Cloud service account with Drive API access
- (Optional) ElevenLabs API key for voice generation

### Installation

```bash
# Clone repository
git clone <your-repo-url>
cd ffmpeg-clipper-api

# Install dependencies
pip install -r requirements.txt

# Download YOLO face detection weights
mkdir -p weights
# Download yolov8n-face.pt from:
# https://github.com/akanametov/yolov8-face/releases
# Place in weights/ directory

# Copy environment template
cp .env.example .env
```

### Running the Server

```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

## API Endpoints

### Health Check

```bash
GET /health
```

**Response:**
```json
{"ok": true}
```

---

### Video Endpoints

#### POST `/api/v1/generate-clips`

Generate vertical clips from horizontal video with AI face tracking.

**Request:**
```json
{
  "google_drive": {
    "credentials": {
      "type": "service_account",
      "project_id": "...",
      "private_key": "...",
      "client_email": "..."
    },
    "source_file_id": "GDRIVE_VIDEO_ID",
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

**Immediate Response:** `202 Accepted`

**Webhook Payload:**
```json
{
  "status": "success",
  "clips": [
    {
      "drive_url": "https://drive.google.com/file/d/ID1/view",
      "drive_file_id": "ID1"
    },
    {
      "drive_url": "https://drive.google.com/file/d/ID2/view",
      "drive_file_id": "ID2"
    }
  ]
}
```

---

#### POST `/api/v1/ffmpeg-compose`

Multi-task endpoint for subtitle burn-in or image slideshow.

**Task 1: Add Captions**
```json
{
  "task": "add_captions",
  "google_drive": {
    "credentials": { "type": "service_account", "...": "..." },
    "video_file_id": "GDRIVE_VIDEO_ID",
    "srt_file_id": "GDRIVE_SRT_ID",
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

**Task 2: Stitch Images**
```json
{
  "task": "stitch_images",
  "google_drive": {
    "credentials": { "type": "service_account", "...": "..." },
    "image_ids": ["IMG_1", "IMG_2", "IMG_3"],
    "audio_id": "AUDIO_ID",
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

**Webhook Payload:**
```json
{
  "status": "success",
  "composed_media": {
    "drive_url": "https://drive.google.com/file/d/ID/view",
    "drive_file_id": "ID"
  }
}
```

---

### Audio Endpoints

#### POST `/api/v1/audio/transcribe`

Transcribe video/audio to SRT subtitles.

**Request:**
```json
{
  "google_drive": {
    "credentials": { "type": "service_account", "...": "..." },
    "source_file_id": "VIDEO_OR_AUDIO_ID",
    "target_folder_id": "GDRIVE_FOLDER_ID"
  },
  "transcription_settings": {
    "model_size": "base",
    "compute_type": "int8",
    "language_hint": "en"
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Webhook Payload:**
```json
{
  "status": "success",
  "srt_file_id": "CAPTIONS_SRT_ID",
  "srt_url": "https://drive.google.com/file/d/ID/view",
  "text_summary": "Full transcript text..."
}
```

---

#### POST `/api/v1/audio/generate-voice`

Generate speech from text using ElevenLabs.

**Request:**
```json
{
  "text_script": "Welcome to the future of AI automation...",
  "google_drive": {
    "credentials": { "type": "service_account", "...": "..." },
    "target_folder_id": "GDRIVE_FOLDER_ID"
  },
  "elevenlabs_settings": {
    "api_key": "ELEVENLABS_API_KEY",
    "voice_id": "Rachel",
    "model_id": "eleven_multilingual_v2"
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Webhook Payload:**
```json
{
  "status": "success",
  "audio_file_id": "VOICEOVER_MP3_ID",
  "audio_url": "https://drive.google.com/file/d/ID/view",
  "duration_seconds": 12.5
}
```

---

#### POST `/api/v1/audio/edit`

Edit audio with trim, merge, and volume operations.

**Request:**
```json
{
  "google_drive": {
    "credentials": { "type": "service_account", "...": "..." },
    "source_file_id": "AUDIO_FILE_ID",
    "target_folder_id": "GDRIVE_FOLDER_ID"
  },
  "operations": [
    { "type": "trim", "start_ms": 0, "end_ms": 30000 },
    { "type": "volume", "adjustment_db": 3.0 },
    { "type": "merge", "additional_file_ids": ["INTRO_ID", "OUTRO_ID"] }
  ],
  "output_format": "mp3",
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Operations:**
- `trim` - Cut audio to time range (milliseconds)
- `volume` - Adjust loudness (+3.0 = louder, -5.0 = quieter)
- `merge` - Concatenate additional files (executed sequentially in array order)

**Webhook Payload:**
```json
{
  "status": "success",
  "edited_file_id": "EDITED_AUDIO_ID",
  "edited_url": "https://drive.google.com/file/d/ID/view",
  "duration_seconds": 45.2
}
```

---

### Error Handling

All endpoints send error webhooks on failure:

```json
{
  "status": "error",
  "error_message": "FFmpeg failed: width not divisible by 2"
}
```

## n8n Integration

### Example Workflow

1. **HTTP Request Node** - POST to API endpoint
2. **Webhook Node** - Listen for callback
3. **Download Node** - Fetch result from Drive URL

### Webhook Configuration

```javascript
// n8n webhook URL format
https://your-n8n-instance.com/webhook/unique-identifier
```

The API will POST the result to this URL when processing completes.

## Deployment

### Docker (Recommended for Proxmox)

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY weights/ ./weights/

# Expose port
EXPOSE 8000

# Run server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Resource Requirements

- CPU: 2 vCPU
- RAM: 4GB (int8 Whisper quantization)
- Storage: 10GB NVMe
- Network: Outbound to Google Drive, ElevenLabs API

## Troubleshooting

### YOLO Model Not Found

```bash
# Download weights
mkdir -p weights
wget https://github.com/akanametov/yolov8-face/releases/download/v0.0.0/yolov8n-face.pt \
  -O weights/yolov8n-face.pt
```

### FFmpeg Not Installed

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

### Google Drive Authentication Fails

- Verify service account has Drive API enabled
- Check service account email has access to target folder
- Ensure credentials JSON is complete and valid

### ElevenLabs API Errors

- Verify API key is valid
- Check voice_id exists in your account
- Monitor API quota/rate limits

## License

MIT

## Support

For issues and feature requests, please open a GitHub issue.
