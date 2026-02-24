"""Intelligent viral shorts generator using AI scene detection and virality scoring."""

import logging
import subprocess
import re
from typing import List, Tuple, Dict
from pathlib import Path

import cv2
import numpy as np
from faster_whisper import WhisperModel

from app.services.transcription import get_whisper_model
from app.services.cutter import get_yolo_model

logger = logging.getLogger(__name__)

# Viral keywords that indicate engaging content
VIRAL_KEYWORDS = {
    "high_energy": ["wow", "amazing", "incredible", "unbelievable", "insane", "crazy", "shocking"],
    "emotional": ["love", "hate", "fear", "surprised", "excited", "angry", "happy", "sad"],
    "call_to_action": ["watch", "look", "check", "listen", "see", "wait", "stop"],
    "controversy": ["wrong", "right", "worst", "best", "never", "always", "secret", "truth"],
    "questions": ["why", "how", "what", "when", "where", "who"],
}


def get_video_metadata(video_path: str) -> Dict[str, float]:
    """
    Get video duration and frame rate.

    Args:
        video_path: Path to video file

    Returns:
        Dict with duration and fps
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = frame_count / fps if fps > 0 else 0
    cap.release()

    logger.info(f"Video metadata: {duration:.2f}s, {fps:.2f} fps")
    return {"duration": duration, "fps": fps}


def detect_scenes(video_path: str, threshold: float = 0.3) -> List[float]:
    """
    Detect scene changes using FFmpeg.

    Args:
        video_path: Path to video file
        threshold: Scene change threshold (0-1)

    Returns:
        List of timestamps where scenes change
    """
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, stderr=subprocess.STDOUT)
    output = result.stdout

    # Parse scene change timestamps from FFmpeg output
    scene_times = []
    pattern = r"pts_time:(\d+\.?\d*)"

    for match in re.finditer(pattern, output):
        timestamp = float(match.group(1))
        scene_times.append(timestamp)

    logger.info(f"Detected {len(scene_times)} scene changes")
    return sorted(scene_times)


def transcribe_with_timestamps(
    video_path: str,
    model_size: str = "base",
    compute_type: str = "int8"
) -> List[Dict]:
    """
    Transcribe video and return segments with timestamps and text.

    Args:
        video_path: Path to video file
        model_size: Whisper model size
        compute_type: Quantization type

    Returns:
        List of segment dicts with start, end, text
    """
    # Extract audio
    audio_path = str(Path(video_path).with_suffix(".wav"))
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # Transcribe
    model = get_whisper_model(model_size, compute_type)
    segments, _ = model.transcribe(audio_path, vad_filter=True)

    transcription = []
    for segment in segments:
        transcription.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip().lower()
        })

    logger.info(f"Transcribed {len(transcription)} segments")
    return transcription


def calculate_speech_energy(segments: List[Dict], start: float, end: float) -> float:
    """
    Calculate speech energy (words per second) in a time range.

    Args:
        segments: Transcription segments
        start: Start time
        end: End time

    Returns:
        Speech energy score (0-1)
    """
    words_in_range = 0
    for seg in segments:
        if seg["start"] >= start and seg["end"] <= end:
            words_in_range += len(seg["text"].split())

    duration = end - start
    words_per_second = words_in_range / duration if duration > 0 else 0

    # Normalize: 3+ words/second = high energy
    return min(words_per_second / 3.0, 1.0)


def calculate_face_presence(
    video_path: str,
    start: float,
    end: float,
    sample_frames: int = 10
) -> float:
    """
    Calculate face presence score in a time range.

    Args:
        video_path: Path to video
        start: Start time
        end: End time
        sample_frames: Number of frames to sample

    Returns:
        Face presence score (0-1)
    """
    model = get_yolo_model()
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)

    start_frame = int(start * fps)
    end_frame = int(end * fps)
    frame_range = end_frame - start_frame

    if frame_range <= 0:
        return 0.0

    sample_interval = max(1, frame_range // sample_frames)
    faces_detected = 0

    for i in range(0, frame_range, sample_interval):
        frame_num = start_frame + i
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()

        if not ret:
            break

        results = model(frame, verbose=False)
        if len(results[0].boxes) > 0:
            faces_detected += 1

    cap.release()

    face_score = faces_detected / sample_frames
    logger.debug(f"Face presence {start:.1f}-{end:.1f}s: {face_score:.2f}")
    return face_score


def count_scene_changes(scene_times: List[float], start: float, end: float) -> int:
    """Count scene changes in a time range."""
    return sum(1 for t in scene_times if start <= t <= end)


def extract_keywords(segments: List[Dict], start: float, end: float) -> List[str]:
    """
    Extract viral keywords from transcription in time range.

    Args:
        segments: Transcription segments
        start: Start time
        end: End time

    Returns:
        List of detected viral keywords
    """
    text_in_range = []
    for seg in segments:
        if seg["start"] >= start and seg["end"] <= end:
            text_in_range.append(seg["text"])

    full_text = " ".join(text_in_range)
    detected_keywords = []

    for category, keywords in VIRAL_KEYWORDS.items():
        for keyword in keywords:
            if keyword in full_text:
                detected_keywords.append(keyword)

    return detected_keywords


def calculate_virality_score(
    video_path: str,
    start: float,
    end: float,
    transcription: List[Dict],
    scene_times: List[float],
    weights: Dict[str, float]
) -> Tuple[float, List[str]]:
    """
    Calculate virality score for a clip segment.

    Args:
        video_path: Path to video
        start: Start time
        end: End time
        transcription: Transcription segments
        scene_times: Scene change timestamps
        weights: Scoring weights

    Returns:
        Tuple of (score, keywords)
    """
    # Speech energy (fast-paced dialogue)
    speech_score = calculate_speech_energy(transcription, start, end)

    # Face presence (engagement)
    face_score = calculate_face_presence(video_path, start, end)

    # Scene changes (visual dynamics)
    scene_count = count_scene_changes(scene_times, start, end)
    scene_score = min(scene_count / 3.0, 1.0)  # 3+ changes = high score

    # Viral keywords
    keywords = extract_keywords(transcription, start, end)
    keyword_score = min(len(keywords) / 5.0, 1.0)  # 5+ keywords = high score

    # Weighted total
    total_score = (
        speech_score * weights.get("speech_energy_weight", 0.3) +
        face_score * weights.get("face_presence_weight", 0.2) +
        scene_score * weights.get("scene_change_weight", 0.2) +
        keyword_score * weights.get("caption_keywords_weight", 0.3)
    )

    logger.info(
        f"Segment {start:.1f}-{end:.1f}s: "
        f"speech={speech_score:.2f}, face={face_score:.2f}, "
        f"scenes={scene_score:.2f}, keywords={keyword_score:.2f} "
        f"→ total={total_score:.2f}"
    )

    return total_score, keywords


def generate_candidate_segments(
    duration: float,
    transcription: List[Dict],
    target_duration: int,
    min_duration: int,
    max_duration: int
) -> List[Tuple[float, float]]:
    """
    Generate candidate clip segments based on transcription boundaries.

    Args:
        duration: Total video duration
        transcription: Transcription segments
        target_duration: Target clip duration
        min_duration: Minimum clip duration
        max_duration: Maximum clip duration

    Returns:
        List of (start, end) tuples
    """
    candidates = []

    # Use transcription segment boundaries as natural cut points
    for i, seg in enumerate(transcription):
        start = seg["start"]
        potential_end = start + target_duration

        # Find a good end point near target duration
        for j in range(i, len(transcription)):
            seg_end = transcription[j]["end"]

            if min_duration <= (seg_end - start) <= max_duration:
                # Found a good segment
                if abs(seg_end - start - target_duration) < 5:  # Within 5s of target
                    candidates.append((start, seg_end))
                    break

    # Also add sliding window candidates if transcription is sparse
    if len(candidates) < 10:
        for start in range(0, int(duration), target_duration // 2):
            end = min(start + target_duration, duration)
            if min_duration <= (end - start) <= max_duration:
                candidates.append((float(start), float(end)))

    logger.info(f"Generated {len(candidates)} candidate segments")
    return candidates


def select_top_segments(
    video_path: str,
    candidates: List[Tuple[float, float]],
    transcription: List[Dict],
    scene_times: List[float],
    max_clips: int,
    weights: Dict[str, float]
) -> List[Dict]:
    """
    Score and select top segments for shorts.

    Args:
        video_path: Path to video
        candidates: Candidate (start, end) tuples
        transcription: Transcription segments
        scene_times: Scene change timestamps
        max_clips: Maximum number of clips to select
        weights: Scoring weights

    Returns:
        List of selected segment dicts with scores
    """
    scored_segments = []

    for start, end in candidates:
        score, keywords = calculate_virality_score(
            video_path,
            start,
            end,
            transcription,
            scene_times,
            weights
        )

        scored_segments.append({
            "start": start,
            "end": end,
            "duration": end - start,
            "score": score,
            "keywords": keywords
        })

    # Sort by score and select top N
    scored_segments.sort(key=lambda x: x["score"], reverse=True)
    selected = scored_segments[:max_clips]

    logger.info(f"Selected top {len(selected)} segments (scores: {[s['score'] for s in selected]})")

    return selected
