# Video & Audio Processing API

FastAPI microservice for automated video and audio processing with Google Drive integration. Perfect for n8n workflows and automation.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- FFmpeg (`brew install ffmpeg` or `apt install ffmpeg`)
- Google Drive credentials (OAuth2 or Service Account)

### Installation

```bash
# Clone and install
git clone <your-repo-url>
cd ffmpeg-clipper-api
pip install -r requirements.txt

# Run server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Server will run at `http://localhost:8000`
API docs at `http://localhost:8000/docs`

---

## 📋 Features

### 🎬 Smart Clips (AI Viral Shorts Generator)
Unified endpoint for generating viral YouTube Shorts from long videos.

**3 Operating Modes:**
- **analyze_only** - Preview best moments with AI scoring (no clips generated)
- **auto_generate** - AI finds and generates viral clips automatically
- **manual_generate** - Generate clips from your specified timestamps

**3 Crop Modes:**
- **auto** - Smart detection (crop if people fit, else scale_pad) *experimental*
- **crop** - Zoom and crop to fill 9:16 frame (best for single person)
- **scale_pad** - Fit full video with black bars (best for multi-person videos)

**AI Features:**
- Virality scoring (speech energy, face presence, scene dynamics, keywords)
- Face/person detection with YOLOv8
- Automatic subtitle generation
- Scene detection and selection

### 🎥 Other Video Operations
- **Subtitle Burn-In** - Add styled captions using FFmpeg
- **Image Slideshow** - Create videos from images with Ken Burns effect

### 🎙️ Audio Operations
- **Speech-to-Text** - Transcribe using faster-whisper (CPU-optimized)
- **Text-to-Speech** - Generate voiceovers with ElevenLabs
- **Audio Editing** - Trim, merge, adjust volume

---

## 📡 API Endpoints

### Health Check
```bash
GET /health
# Response: {"ok": true}
```

---

### POST `/api/v1/smart-clips`

Generate viral shorts from long-form content.

#### Mode 1: Analyze Only (Preview Best Moments)

```json
{
  "google_drive": {
    "credentials": {
      "type": "oauth2",
      "client_id": "...",
      "client_secret": "...",
      "refresh_token": "..."
    },
    "source_file_id": "GOOGLE_DRIVE_VIDEO_ID",
    "target_folder_id": "GOOGLE_DRIVE_FOLDER_ID"
  },
  "settings": {
    "mode": "analyze_only",
    "target_duration": 30,
    "max_clips": 5,
    "speech_energy_weight": 0.3,
    "face_presence_weight": 0.2,
    "scene_change_weight": 0.2,
    "caption_keywords_weight": 0.3
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Webhook Response:**
```json
{
  "status": "success",
  "mode": "analyze_only",
  "segments": [
    {
      "segment_number": 1,
      "start_time": 45.2,
      "end_time": 75.8,
      "duration": 30.6,
      "virality_score": 0.87,
      "keywords": ["amazing", "wow"],
      "speech_energy": 0.92,
      "face_presence": 0.85,
      "scene_changes": 3
    }
  ],
  "total_segments": 5
}
```

#### Mode 2: Auto-Generate (AI Selects & Creates Clips)

```json
{
  "google_drive": { /* same as above */ },
  "settings": {
    "mode": "auto_generate",
    "target_duration": 30,
    "max_clips": 3,
    "add_captions": true,
    "aspect_ratio": "9:16",
    "crop_mode": "scale_pad"
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Webhook Response:**
```json
{
  "status": "success",
  "mode": "auto_generate",
  "clips": [
    {
      "clip_number": 1,
      "drive_url": "https://drive.google.com/file/d/ID1/view",
      "drive_file_id": "ID1",
      "start_time": 45.2,
      "end_time": 75.8,
      "duration": 30.6,
      "virality_score": 0.87,
      "keywords": ["amazing", "wow"]
    }
  ],
  "total_clips": 3
}
```

#### Mode 3: Manual Generate (User-Specified Timestamps)

```json
{
  "google_drive": { /* same as above */ },
  "settings": {
    "mode": "manual_generate",
    "manual_timestamps": [
      {"start": 10, "end": 40},
      {"start": 60, "end": 90}
    ],
    "add_captions": false,
    "aspect_ratio": "9:16",
    "crop_mode": "scale_pad"
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Webhook Response:**
```json
{
  "status": "success",
  "mode": "manual_generate",
  "clips": [
    {
      "clip_number": 1,
      "drive_url": "https://drive.google.com/file/d/ID1/view",
      "drive_file_id": "ID1",
      "start_time": 10.0,
      "end_time": 40.0,
      "duration": 30.0
    }
  ]
}
```

#### Settings Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | string | `"auto_generate"` | `analyze_only`, `auto_generate`, or `manual_generate` |
| `manual_timestamps` | array | `null` | Required for `manual_generate` mode |
| `target_duration` | int | `30` | Target clip length in seconds |
| `max_clips` | int | `3` | Maximum clips to generate |
| `add_captions` | bool | `true` | Auto-generate subtitles |
| `aspect_ratio` | string | `"9:16"` | Output aspect ratio |
| `crop_mode` | string | `"auto"` | `auto`, `crop`, or `scale_pad` |
| `apply_face_tracking` | bool | `true` | Track faces when using crop mode |
| `speech_energy_weight` | float | `0.3` | AI scoring weight (0-1) |
| `face_presence_weight` | float | `0.2` | AI scoring weight (0-1) |
| `scene_change_weight` | float | `0.2` | AI scoring weight (0-1) |
| `caption_keywords_weight` | float | `0.3` | AI scoring weight (0-1) |

**Crop Mode Guide:**
- **`auto`** *(experimental)* - Detects people and chooses best mode. May crash on large files.
- **`crop`** - Crops and zooms to fill frame. Use for single-person videos.
- **`scale_pad`** - Fits full video with black bars. **Recommended for multi-person videos.**

See [CROP_MODES.md](CROP_MODES.md) for detailed documentation.

---

### POST `/api/v1/ffmpeg-compose`

Add captions or create slideshows.

**Task 1: Add Captions**
```json
{
  "task": "add_captions",
  "google_drive": {
    "credentials": { /* ... */ },
    "video_file_id": "VIDEO_ID",
    "srt_file_id": "SRT_ID",
    "target_folder_id": "FOLDER_ID"
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
    "credentials": { /* ... */ },
    "image_ids": ["IMG1", "IMG2", "IMG3"],
    "audio_id": "AUDIO_ID",
    "target_folder_id": "FOLDER_ID"
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

---

### POST `/api/v1/audio/transcribe`

Transcribe video/audio to SRT subtitles.

```json
{
  "google_drive": {
    "credentials": { /* ... */ },
    "source_file_id": "VIDEO_OR_AUDIO_ID",
    "target_folder_id": "FOLDER_ID"
  },
  "transcription_settings": {
    "model_size": "base",
    "compute_type": "int8",
    "language_hint": "en"
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Response:**
```json
{
  "status": "success",
  "srt_file_id": "SRT_ID",
  "srt_url": "https://drive.google.com/file/d/ID/view",
  "text_summary": "Full transcript..."
}
```

---

### POST `/api/v1/audio/generate-voice`

Generate speech using ElevenLabs.

```json
{
  "text_script": "Your voiceover text here...",
  "google_drive": {
    "credentials": { /* ... */ },
    "target_folder_id": "FOLDER_ID"
  },
  "elevenlabs_settings": {
    "api_key": "ELEVENLABS_API_KEY",
    "voice_id": "Rachel",
    "model_id": "eleven_multilingual_v2"
  },
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

---

### POST `/api/v1/audio/edit`

Trim, merge, or adjust volume.

```json
{
  "google_drive": {
    "credentials": { /* ... */ },
    "source_file_id": "AUDIO_ID",
    "target_folder_id": "FOLDER_ID"
  },
  "operations": [
    {"type": "trim", "start_ms": 0, "end_ms": 30000},
    {"type": "volume", "adjustment_db": 3.0}
  ],
  "output_format": "mp3",
  "webhook_callback": "https://n8n.host/webhook/abc123"
}
```

**Available Operations:**
- `trim` - Cut audio to time range (milliseconds)
- `volume` - Adjust loudness (+3.0 = louder, -5.0 = quieter)
- `merge` - Concatenate additional files

---

## 🔧 Configuration

### Environment Variables

Create `.env` file:
```bash
# Optional - YOLO weights path
YOLO_WEIGHTS=yolov8n.pt
```

### Google Drive Credentials

**Option 1: OAuth2** (User authentication)
```json
{
  "type": "oauth2",
  "client_id": "...",
  "client_secret": "...",
  "refresh_token": "..."
}
```

**Option 2: Service Account** (Server-to-server)
```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key": "...",
  "client_email": "..."
}
```

---

## 🐳 Deployment

### Docker

```dockerfile
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Resource Requirements
- **CPU:** 2 vCPU minimum
- **RAM:** 4GB (for Whisper transcription)
- **Storage:** 10GB
- **Network:** Access to Google Drive API, ElevenLabs API

---

## 🔍 Architecture

**Async Pattern:**
All endpoints return `202 Accepted` immediately. Results are sent to webhook callback when processing completes.

**Workflow:**
1. Client POSTs request → Get `202 Accepted` response
2. API processes in background
3. API POSTs result to webhook URL
4. Client receives result with Google Drive URLs

**Isolation:**
Each job runs in isolated `/tmp/job_<uuid>/` directory with automatic cleanup.

---

## 🛠️ Troubleshooting

### YOLOv8 Model Download

The YOLOv8n model auto-downloads on first use. To pre-download:

```bash
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

### FFmpeg Not Found

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

### Google Drive Errors

- Verify service account has Drive API enabled
- Check folder permissions for service account email
- Ensure credentials JSON is complete

### Auto Crop Mode Crashes

Auto mode with YOLO detection is resource-intensive. For multi-person videos, use:
```json
{"crop_mode": "scale_pad"}
```

---

## 📚 Additional Documentation

- [CROP_MODES.md](CROP_MODES.md) - Detailed crop mode guide with examples

---

## 📄 License

MIT

---

## 💬 Support

For issues and feature requests, open a GitHub issue.
