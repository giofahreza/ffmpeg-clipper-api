"""Models for the /audio/generate-voice endpoint."""

from typing import Literal
from pydantic import BaseModel

from app.models.common import GoogleDriveCredentials


class VoiceDriveConfig(BaseModel):
    """Google Drive configuration for voice generation."""

    credentials: GoogleDriveCredentials
    target_folder_id: str


class ElevenLabsSettings(BaseModel):
    """ElevenLabs API configuration."""

    api_key: str
    voice_id: str = "Rachel"
    model_id: str = "eleven_multilingual_v2"


class VoiceRequest(BaseModel):
    """Request payload for /audio/generate-voice."""

    text_script: str
    google_drive: VoiceDriveConfig
    elevenlabs_settings: ElevenLabsSettings
    webhook_callback: str


class VoiceSuccessPayload(BaseModel):
    """Success webhook payload."""

    status: Literal["success"] = "success"
    audio_file_id: str
    audio_url: str
    duration_seconds: float
