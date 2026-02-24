"""Face-tracking crop engine using YOLOv8 and Savitzky-Golay smoothing."""

import os
import logging
import subprocess
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from scipy.signal import savgol_filter
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# Singleton YOLO model (loaded once per process)
_yolo_model = None


def get_yolo_model():
    """Get or initialize the YOLO detection model."""
    global _yolo_model

    if _yolo_model is None:
        # Use standard YOLOv8n for person detection (auto-downloads if needed)
        weights_path = os.getenv("YOLO_WEIGHTS", "yolov8n.pt")
        logger.info(f"Loading YOLO model: {weights_path}")
        _yolo_model = YOLO(weights_path)

    return _yolo_model


def extract_segment(
    source_video: str,
    start: float,
    end: float,
    output_path: str
) -> None:
    """
    Extract video segment using stream copy (no re-encode).

    Args:
        source_video: Path to source video
        start: Start time in seconds
        end: End time in seconds
        output_path: Output file path
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", source_video,
        "-t", str(end - start),
        "-c", "copy",
        output_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Extracted segment {start}-{end}s to {output_path}")


def detect_faces_in_video(video_path: str) -> List[Tuple[int, int]]:
    """
    Detect person centers in video frames using YOLO.

    Args:
        video_path: Path to video file

    Returns:
        List of (center_x, center_y) tuples for each frame
    """
    model = get_yolo_model()
    cap = cv2.VideoCapture(video_path)

    centers = []
    prev_center = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Run YOLO detection (class 0 = person)
        results = model(frame, verbose=False, classes=[0])

        if len(results[0].boxes) > 0:
            # Use first detected person
            box = results[0].boxes[0].xyxy[0].cpu().numpy()
            center_x = int((box[0] + box[2]) / 2)
            center_y = int((box[1] + box[3]) / 2)
            prev_center = (center_x, center_y)
        else:
            # No person detected, use previous center
            if prev_center:
                center_x, center_y = prev_center
            else:
                # Default to frame center
                height, width = frame.shape[:2]
                center_x, center_y = width // 2, height // 2

        centers.append((center_x, center_y))

    cap.release()
    return centers


def apply_savitzky_golay_smoothing(
    centers: List[Tuple[int, int]],
    window_length: int = 21,
    polyorder: int = 3
) -> List[Tuple[int, int]]:
    """
    Smooth face center trajectory using Savitzky-Golay filter.

    Args:
        centers: List of (x, y) coordinates
        window_length: Filter window size (must be odd)
        polyorder: Polynomial order

    Returns:
        Smoothed centers
    """
    if len(centers) < window_length:
        return centers

    x_coords = [c[0] for c in centers]
    y_coords = [c[1] for c in centers]

    x_smooth = savgol_filter(x_coords, window_length, polyorder)
    y_smooth = savgol_filter(y_coords, window_length, polyorder)

    return [(int(x), int(y)) for x, y in zip(x_smooth, y_smooth)]


def generate_crop_commands(
    centers: List[Tuple[int, int]],
    video_width: int,
    video_height: int,
    crop_width: int,
    crop_height: int
) -> str:
    """
    Generate FFmpeg sendcmd file for per-frame cropping.

    Args:
        centers: Smoothed face centers
        video_width: Source video width
        video_height: Source video height
        crop_width: Target crop width
        crop_height: Target crop height

    Returns:
        Path to sendcmd file
    """
    sendcmd_lines = []

    for frame_num, (cx, cy) in enumerate(centers):
        # Calculate crop coordinates (centered on face)
        crop_x = max(0, min(cx - crop_width // 2, video_width - crop_width))
        crop_y = max(0, min(cy - crop_height // 2, video_height - crop_height))

        # FFmpeg sendcmd format: [frame_number] crop x [x_value], crop y [y_value]
        sendcmd_lines.append(f"{frame_num} [enter] crop x {crop_x}, crop y {crop_y};")

    sendcmd_content = "\n".join(sendcmd_lines)
    sendcmd_path = "/tmp/crop_commands.txt"

    with open(sendcmd_path, "w") as f:
        f.write(sendcmd_content)

    return sendcmd_path


def analyze_face_spread(video_path: str, aspect_ratio: str = "9:16") -> dict:
    """
    Analyze if faces in video can fit within target aspect ratio crop.

    Args:
        video_path: Path to video file
        aspect_ratio: Target aspect ratio (e.g., "9:16")

    Returns:
        {
            "can_crop": bool,
            "has_faces": bool,
            "face_spread_ratio": float,
            "recommended_mode": "crop" or "scale_pad"
        }
    """
    try:
        model = get_yolo_model()
    except (FileNotFoundError, Exception) as e:
        logger.warning(f"YOLO model not available ({e}), defaulting to scale_pad mode")
        return {
            "can_crop": False,
            "has_faces": False,
            "face_spread_ratio": 0.0,
            "recommended_mode": "scale_pad",
            "error": str(e)
        }

    cap = cv2.VideoCapture(video_path)

    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Calculate crop dimensions for target aspect ratio
    ar_width, ar_height = map(int, aspect_ratio.split(":"))
    crop_height = video_height
    crop_width = int(crop_height * ar_width / ar_height)

    # Sample only 3 strategic frames (beginning, middle, end) for speed
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames_to_check = [
        total_frames // 4,      # 25% into video
        total_frames // 2,      # Middle
        3 * total_frames // 4   # 75% into video
    ]

    all_face_boxes = []

    for target_frame in frames_to_check:
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()

        if ret:
            # Detect people only (class 0)
            results = model(frame, verbose=False, classes=[0])

            for box in results[0].boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                all_face_boxes.append((x1, y1, x2, y2))

    cap.release()

    # No faces detected
    if len(all_face_boxes) == 0:
        logger.info("No faces detected - recommending scale_pad mode")
        return {
            "can_crop": False,
            "has_faces": False,
            "face_spread_ratio": 0.0,
            "recommended_mode": "scale_pad"
        }

    # Calculate bounding box containing all faces
    min_x = min(box[0] for box in all_face_boxes)
    max_x = max(box[2] for box in all_face_boxes)
    min_y = min(box[1] for box in all_face_boxes)
    max_y = max(box[3] for box in all_face_boxes)

    # Add 20% padding
    padding = 0.2
    face_width = max_x - min_x
    face_height = max_y - min_y
    min_x = max(0, min_x - face_width * padding)
    max_x = min(video_width, max_x + face_width * padding)

    face_spread_width = max_x - min_x
    face_spread_ratio = face_spread_width / crop_width

    # Can crop if faces fit within 9:16 frame (with some tolerance)
    can_crop = face_spread_ratio <= 1.0

    logger.info(f"Face analysis: spread_width={face_spread_width:.0f}, crop_width={crop_width}, ratio={face_spread_ratio:.2f}")
    logger.info(f"Recommended mode: {'crop' if can_crop else 'scale_pad'}")

    return {
        "can_crop": can_crop,
        "has_faces": True,
        "face_spread_ratio": face_spread_ratio,
        "recommended_mode": "crop" if can_crop else "scale_pad"
    }


def create_vertical_clip(
    segment_path: str,
    output_path: str,
    aspect_ratio: str = "9:16",
    apply_face_tracking: bool = True,
    crop_mode: str = "auto"
) -> None:
    """
    Create vertical clip with intelligent auto-detection or manual mode.

    Args:
        segment_path: Path to extracted segment
        output_path: Output clip path
        aspect_ratio: Target aspect ratio (e.g., "9:16")
        apply_face_tracking: Whether to apply YOLO face tracking (only for crop mode)
        crop_mode: "auto" (smart detection), "crop" (force crop), "scale_pad" (force scale)
    """
    # Get video dimensions
    cap = cv2.VideoCapture(segment_path)
    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    # Calculate target dimensions
    ar_width, ar_height = map(int, aspect_ratio.split(":"))
    target_width = ar_width * 120  # 1080 for 9:16
    target_height = ar_height * 120  # 1920 for 9:16

    # Auto-detect best mode
    if crop_mode == "auto":
        analysis = analyze_face_spread(segment_path, aspect_ratio)
        crop_mode = analysis["recommended_mode"]
        logger.info(f"Auto-detected crop mode: {crop_mode} (has_faces={analysis['has_faces']}, can_crop={analysis['can_crop']})")

    if crop_mode == "scale_pad":
        # Scale and pad mode - keeps full video visible with black bars
        # Scale to fit width, then pad height with black bars
        cmd = [
            "ffmpeg", "-y",
            "-i", segment_path,
            "-vf", f"scale={target_width}:-1,pad={target_width}:{target_height}:0:(oh-ih)/2:black",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            output_path
        ]
    else:
        # Crop mode (original behavior)
        crop_height = video_height
        crop_width = int(crop_height * ar_width / ar_height)

        if apply_face_tracking:
            # Face tracking mode
            centers = detect_faces_in_video(segment_path)
            smoothed_centers = apply_savitzky_golay_smoothing(centers)
            sendcmd_path = generate_crop_commands(
                smoothed_centers, video_width, video_height, crop_width, crop_height
            )

            cmd = [
                "ffmpeg", "-y",
                "-i", segment_path,
                "-filter_complex",
                f"sendcmd=f={sendcmd_path},crop={crop_width}:{crop_height}:0:0,scale={target_width}:{target_height}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ]
        else:
            # Static center crop
            crop_x = (video_width - crop_width) // 2
            cmd = [
                "ffmpeg", "-y",
                "-i", segment_path,
                "-vf", f"crop={crop_width}:{crop_height}:{crop_x}:0,scale={target_width}:{target_height}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ]

    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Created vertical clip: {output_path} (mode: {crop_mode})")


def generate_clips(
    source_video: str,
    timestamps: List[Tuple[float, float]],
    job_dir: str,
    aspect_ratio: str = "9:16",
    apply_face_tracking: bool = True
) -> List[str]:
    """
    Generate multiple vertical clips from source video.

    Args:
        source_video: Path to source video
        timestamps: List of (start, end) tuples
        job_dir: Job directory for temp files
        aspect_ratio: Target aspect ratio
        apply_face_tracking: Whether to apply face tracking

    Returns:
        List of output clip paths
    """
    clip_paths = []

    for i, (start, end) in enumerate(timestamps):
        # Extract segment
        segment_path = os.path.join(job_dir, f"segment_{i}.mp4")
        extract_segment(source_video, start, end, segment_path)

        # Create vertical clip
        clip_path = os.path.join(job_dir, f"clip_{i}.mp4")
        create_vertical_clip(segment_path, clip_path, aspect_ratio, apply_face_tracking)

        clip_paths.append(clip_path)

    return clip_paths
