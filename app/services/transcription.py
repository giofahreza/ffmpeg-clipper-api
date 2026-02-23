"""Speech-to-text transcription using faster-whisper."""

import logging
import subprocess
from typing import Tuple
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Singleton Whisper models (loaded once per process)
_whisper_models = {}


def get_whisper_model(model_size: str = "base", compute_type: str = "int8"):
    """
    Get or initialize Whisper model.

    Args:
        model_size: Model size (tiny, base, small, medium, large)
        compute_type: Quantization type (int8, float16, float32)

    Returns:
        WhisperModel instance
    """
    global _whisper_models

    key = f"{model_size}_{compute_type}"

    if key not in _whisper_models:
        logger.info(f"Loading Whisper model: {model_size} ({compute_type})")
        _whisper_models[key] = WhisperModel(
            model_size,
            device="cpu",
            compute_type=compute_type
        )

    return _whisper_models[key]


def extract_audio_from_video(video_path: str, audio_path: str) -> None:
    """
    Extract audio from video file using FFmpeg.

    Args:
        video_path: Input video file
        audio_path: Output WAV file (16kHz mono PCM)
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", "16000",  # 16kHz sample rate (optimal for Whisper)
        "-ac", "1",  # Mono
        audio_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Extracted audio to {audio_path}")


def format_timestamp(seconds: float) -> str:
    """
    Format seconds as SRT timestamp (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds

    Returns:
        SRT-formatted timestamp
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def transcribe_audio(
    audio_path: str,
    model_size: str = "base",
    compute_type: str = "int8",
    language: str = "en"
) -> Tuple[str, str]:
    """
    Transcribe audio file to SRT format.

    Args:
        audio_path: Path to audio file
        model_size: Whisper model size
        compute_type: Quantization type
        language: Language hint

    Returns:
        Tuple of (srt_string, full_text)
    """
    model = get_whisper_model(model_size, compute_type)

    # Transcribe with word-level timestamps
    segments, info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=False,
        vad_filter=True  # Voice activity detection
    )

    logger.info(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")

    # Generate SRT
    srt_lines = []
    full_text = []
    segment_num = 1

    for segment in segments:
        # SRT format:
        # 1
        # 00:00:00,000 --> 00:00:05,000
        # Text goes here
        start_time = format_timestamp(segment.start)
        end_time = format_timestamp(segment.end)
        text = segment.text.strip()

        srt_lines.append(str(segment_num))
        srt_lines.append(f"{start_time} --> {end_time}")
        srt_lines.append(text)
        srt_lines.append("")  # Blank line separator

        full_text.append(text)
        segment_num += 1

    srt_content = "\n".join(srt_lines)
    full_transcript = " ".join(full_text)

    logger.info(f"Transcribed {segment_num - 1} segments")

    return srt_content, full_transcript
