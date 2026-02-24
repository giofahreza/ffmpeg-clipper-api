# Intelligent Crop Mode Documentation

## Overview
The API now features **intelligent auto-detection** that automatically chooses the best cropping strategy based on video content.

## Crop Modes

### 1. `auto` (Recommended - Default)
**Smart detection that automatically chooses the best mode.**

**How it works:**
1. Downloads YOLOv8n model (6.25MB, one-time)
2. Samples 10 frames from your video segment
3. Detects all people in those frames
4. Calculates if everyone fits within a 9:16 crop
5. Decides:
   - ✅ **People fit in 9:16** → Use `crop` mode (zoom in, fill frame)
   - ❌ **People spread too wide OR no people** → Use `scale_pad` mode (keep full video)

**Perfect for:**
- Mixed content (some clips with 1 person, some with 2+ people)
- Unknown video content
- Automated workflows

### 2. `crop` (Force Crop)
**Always crops and zooms to fill the 9:16 frame.**

- Crops center or tracks faces
- Best for single-person videos
- May cut off people at edges if multiple people spread wide

### 3. `scale_pad` (Force Scale)
**Always scales the full video to fit with black bars.**

- No content is cropped
- Black bars on top/bottom
- Best for multi-person side-by-side videos
- Best for landscape scenes

## API Usage

### Example 1: Auto Mode (Recommended)
```bash
curl -X POST http://localhost:4043/api/v1/smart-clips \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "crop_mode": "auto",  # Smart detection
      "apply_face_tracking": true  # Used if auto chooses crop mode
    }
  }'
```

### Example 2: Force Scale & Pad
```bash
curl -X POST http://localhost:4043/api/v1/smart-clips \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "crop_mode": "scale_pad"  # Always keep full video
    }
  }'
```

### Example 3: Force Crop with Face Tracking
```bash
curl -X POST http://localhost:4043/api/v1/smart-clips \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "crop_mode": "crop",  # Always crop
      "apply_face_tracking": true  # Track and follow detected people
    }
  }'
```

## Server Logs

When using `auto` mode, you'll see logs like:

```
2026-02-24 13:55:55 - INFO - Loading YOLO model: yolov8n.pt
2026-02-24 13:56:10 - INFO - Face analysis: spread_width=1200, crop_width=1080, ratio=1.11
2026-02-24 13:56:10 - INFO - Recommended mode: scale_pad
2026-02-24 13:56:10 - INFO - Auto-detected crop mode: scale_pad (has_faces=True, can_crop=False)
2026-02-24 13:56:25 - INFO - Created vertical clip: vertical_1.mp4 (mode: scale_pad)
```

## Performance

- **First run:** 5-10 seconds (downloads YOLO model)
- **Subsequent runs:** +2-3 seconds for auto-detection
- **Manual modes:** No detection overhead

## Current Status

✅ Server running on **port 4043**
✅ Auto-detection implemented
✅ YOLOv8n person detection
✅ 3 crop modes available

## Your Test Video Results

Based on your video (2 people side-by-side):
- **Auto mode** will detect: `has_faces=True, can_crop=False`
- **Recommendation:** `scale_pad`
- **Result:** Full video visible with black bars (no one cropped out)
