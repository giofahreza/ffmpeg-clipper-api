"""Audio editing operations using pydub."""

import logging
from typing import List
from pydub import AudioSegment
from googleapiclient.discovery import Resource

from app.services.gdrive import download_from_google_drive

logger = logging.getLogger(__name__)


def load_audio(file_path: str) -> AudioSegment:
    """
    Load audio file (auto-detects format).

    Args:
        file_path: Path to audio file

    Returns:
        AudioSegment instance
    """
    audio = AudioSegment.from_file(file_path)
    logger.info(f"Loaded audio: {len(audio)}ms, {audio.channels} channels, {audio.frame_rate}Hz")
    return audio


def apply_trim(audio: AudioSegment, start_ms: int, end_ms: int) -> AudioSegment:
    """
    Trim audio to specified range.

    Args:
        audio: Source audio
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds

    Returns:
        Trimmed audio
    """
    trimmed = audio[start_ms:end_ms]
    logger.info(f"Trimmed audio from {start_ms}ms to {end_ms}ms (duration: {len(trimmed)}ms)")
    return trimmed


def apply_volume(audio: AudioSegment, adjustment_db: float) -> AudioSegment:
    """
    Adjust audio volume.

    Args:
        audio: Source audio
        adjustment_db: Volume adjustment in dB (+3.0 = louder, -5.0 = quieter)

    Returns:
        Volume-adjusted audio
    """
    adjusted = audio + adjustment_db
    logger.info(f"Adjusted volume by {adjustment_db:+.1f} dB")
    return adjusted


def apply_merge(
    audio: AudioSegment,
    drive_client: Resource,
    file_ids: List[str],
    job_dir: str
) -> AudioSegment:
    """
    Merge additional audio files from Google Drive.

    Args:
        audio: Base audio
        drive_client: Google Drive API client
        file_ids: List of Drive file IDs to concatenate
        job_dir: Job directory for downloading files

    Returns:
        Merged audio
    """
    merged = audio

    for i, file_id in enumerate(file_ids):
        # Download additional file
        temp_path = f"{job_dir}/merge_{i}.mp3"
        download_from_google_drive(drive_client, file_id, temp_path)

        # Load and concatenate
        additional_audio = load_audio(temp_path)
        merged = merged + additional_audio

    logger.info(f"Merged {len(file_ids)} additional files (total duration: {len(merged)}ms)")
    return merged


def process_operations(
    audio: AudioSegment,
    operations: List[dict],
    job_dir: str,
    drive_client: Resource = None
) -> AudioSegment:
    """
    Execute audio operations sequentially.

    Args:
        audio: Source audio
        operations: List of operation dictionaries
        job_dir: Job directory
        drive_client: Google Drive client (required for merge)

    Returns:
        Processed audio
    """
    result = audio

    for op in operations:
        op_type = op.get("type")

        if op_type == "trim":
            result = apply_trim(result, op["start_ms"], op["end_ms"])

        elif op_type == "volume":
            result = apply_volume(result, op["adjustment_db"])

        elif op_type == "merge":
            if not drive_client:
                raise ValueError("Drive client required for merge operation")
            result = apply_merge(result, drive_client, op["additional_file_ids"], job_dir)

        else:
            logger.warning(f"Unknown operation type: {op_type}")

    return result


def export_audio(audio: AudioSegment, output_path: str, format: str = "mp3") -> None:
    """
    Export audio to file.

    Args:
        audio: Audio to export
        output_path: Output file path
        format: Output format (mp3, wav, flac)
    """
    audio.export(output_path, format=format)
    logger.info(f"Exported audio to {output_path} ({format} format)")


def get_duration_seconds(audio: AudioSegment) -> float:
    """
    Get audio duration in seconds.

    Args:
        audio: AudioSegment instance

    Returns:
        Duration in seconds
    """
    return len(audio) / 1000.0
