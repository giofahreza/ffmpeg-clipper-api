"""Models for the /ffmpeg-compose endpoint (multi-task)."""

from typing import Annotated, List, Literal
from pydantic import BaseModel, Field

from app.models.common import GoogleDriveCredentials


# Task 1: add_captions

class AddCaptionsDriveConfig(BaseModel):
    """Google Drive configuration for caption burn-in."""

    credentials: GoogleDriveCredentials
    video_file_id: str
    srt_file_id: str
    target_folder_id: str


class CaptionStyling(BaseModel):
    """ASS subtitle styling configuration."""

    font: str = "Montserrat-Black"
    font_size: int = 24
    primary_color: str = "&H00FFFF&"  # ASS color format
    alignment: int = 2  # Bottom center
    margin_v: int = 150  # Vertical margin from bottom


class AddCaptionsRequest(BaseModel):
    """Request for add_captions task."""

    task: Literal["add_captions"] = "add_captions"
    google_drive: AddCaptionsDriveConfig
    caption_styling: CaptionStyling
    webhook_callback: str


# Task 2: stitch_images

class StitchImagesDriveConfig(BaseModel):
    """Google Drive configuration for image slideshow."""

    credentials: GoogleDriveCredentials
    image_ids: List[str]
    audio_id: str
    target_folder_id: str


class StitchOperations(BaseModel):
    """Image slideshow configuration."""

    resolution: str = "1080x1920"  # width x height
    duration_per_image: float = 4.5  # seconds
    transition: Literal["crossfade"] = "crossfade"
    apply_ken_burns: bool = True


class StitchImagesRequest(BaseModel):
    """Request for stitch_images task."""

    task: Literal["stitch_images"] = "stitch_images"
    google_drive: StitchImagesDriveConfig
    operations: StitchOperations
    webhook_callback: str


# Discriminated union for multi-task endpoint

FFmpegComposeRequest = Annotated[
    AddCaptionsRequest | StitchImagesRequest,
    Field(discriminator="task")
]


# Webhook responses

class ComposedMediaResult(BaseModel):
    """Result of composition operation."""

    drive_url: str
    drive_file_id: str


class FFmpegComposeSuccessPayload(BaseModel):
    """Success webhook payload."""

    status: Literal["success"] = "success"
    composed_media: ComposedMediaResult
