"""Models for the /audio/transcribe endpoint."""

from typing import Literal
from pydantic import BaseModel

from app.models.common import GoogleDriveCredentials


class TranscribeDriveConfig(BaseModel):
    """Google Drive configuration for transcription."""

    credentials: GoogleDriveCredentials
    source_file_id: str  # Video or audio file
    target_folder_id: str


class TranscriptionSettings(BaseModel):
    """Whisper transcription configuration."""

    model_size: Literal["tiny", "base", "small", "medium", "large"] = "base"
    compute_type: Literal["int8", "float16", "float32"] = "int8"
    language_hint: str = "en"


class TranscribeRequest(BaseModel):
    """Request payload for /audio/transcribe."""

    google_drive: TranscribeDriveConfig
    transcription_settings: TranscriptionSettings
    webhook_callback: str


class TranscribeSuccessPayload(BaseModel):
    """Success webhook payload."""

    status: Literal["success"] = "success"
    srt_file_id: str
    srt_url: str
    text_summary: str  # Full transcript text
