"""Models for the /audio/edit endpoint."""

from typing import Annotated, List, Literal
from pydantic import BaseModel, Field

from app.models.common import GoogleDriveCredentials


class EditDriveConfig(BaseModel):
    """Google Drive configuration for audio editing."""

    credentials: GoogleDriveCredentials
    source_file_id: str
    target_folder_id: str


class TrimOperation(BaseModel):
    """Trim audio to time range."""

    type: Literal["trim"] = "trim"
    start_ms: int  # milliseconds
    end_ms: int    # milliseconds


class VolumeOperation(BaseModel):
    """Adjust audio volume."""

    type: Literal["volume"] = "volume"
    adjustment_db: float  # +3.0 = louder, -5.0 = quieter


class MergeOperation(BaseModel):
    """Merge multiple audio files."""

    type: Literal["merge"] = "merge"
    additional_file_ids: List[str]  # Drive IDs to concatenate


AudioOperation = Annotated[
    TrimOperation | VolumeOperation | MergeOperation,
    Field(discriminator="type")
]


class EditRequest(BaseModel):
    """Request payload for /audio/edit."""

    google_drive: EditDriveConfig
    operations: List[AudioOperation]
    output_format: Literal["mp3", "wav", "flac"] = "mp3"
    webhook_callback: str


class EditSuccessPayload(BaseModel):
    """Success webhook payload."""

    status: Literal["success"] = "success"
    edited_file_id: str
    edited_url: str
    duration_seconds: float
