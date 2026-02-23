"""Models for the /generate-clips endpoint."""

from typing import List, Literal
from pydantic import BaseModel

from app.models.common import GoogleDriveCredentials


class GenerateClipsDriveConfig(BaseModel):
    """Google Drive configuration for clip generation."""

    credentials: GoogleDriveCredentials
    source_file_id: str
    target_folder_id: str


class Timestamp(BaseModel):
    """Time range for clip extraction."""

    start: float  # seconds
    end: float    # seconds


class ProcessingRules(BaseModel):
    """Video processing configuration."""

    aspect_ratio: str = "9:16"
    apply_face_tracking: bool = True
    stabilization_filter: Literal["savitzky-golay"] = "savitzky-golay"


class GenerateClipsRequest(BaseModel):
    """Request payload for /generate-clips."""

    google_drive: GenerateClipsDriveConfig
    timestamps: List[Timestamp]
    processing_rules: ProcessingRules
    webhook_callback: str


class ClipResult(BaseModel):
    """Single clip result."""

    drive_url: str
    drive_file_id: str


class GenerateClipsSuccessPayload(BaseModel):
    """Success webhook payload."""

    status: Literal["success"] = "success"
    clips: List[ClipResult]
