"""Unified smart clips endpoint - combines auto-discovery with manual timestamps."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

from app.models.common import GoogleDriveCredentials


class SmartClipsDriveConfig(BaseModel):
    """Google Drive configuration."""

    credentials: GoogleDriveCredentials
    source_file_id: str
    target_folder_id: str


class ManualTimestamp(BaseModel):
    """Manual timestamp for clip extraction."""

    start: float  # seconds
    end: float    # seconds


class SmartClipsSettings(BaseModel):
    """Flexible settings for smart clip generation."""

    # MODE SELECTION
    mode: Literal["analyze_only", "auto_generate", "manual_generate"] = "auto_generate"

    # Manual timestamps (only used if mode="manual_generate")
    manual_timestamps: Optional[List[ManualTimestamp]] = None

    # Auto-discovery settings (used if mode="analyze_only" or "auto_generate")
    target_duration: int = 30
    min_duration: int = 20
    max_duration: int = 45
    max_clips: int = 3

    # Virality scoring weights (used in auto modes)
    speech_energy_weight: float = 0.3
    face_presence_weight: float = 0.2
    scene_change_weight: float = 0.2
    caption_keywords_weight: float = 0.3

    # Output settings (used in generate modes)
    add_captions: bool = True
    aspect_ratio: str = "9:16"
    apply_face_tracking: bool = True
    crop_mode: Literal["auto", "crop", "scale_pad"] = Field(
        default="auto",
        description="auto: smart detect (crop if people fit, else scale_pad) | crop: force crop | scale_pad: force scale with black bars"
    )

    # Caption styling (if add_captions=True)
    caption_font: str = "Montserrat-Black"
    caption_font_size: int = 28
    caption_color: str = "&H00FFFF&"


class SmartClipsRequest(BaseModel):
    """Request payload for /smart-clips."""

    google_drive: SmartClipsDriveConfig
    settings: SmartClipsSettings
    webhook_callback: str


class AnalyzedSegment(BaseModel):
    """Analyzed segment (for analyze_only mode)."""

    segment_number: int
    start_time: float
    end_time: float
    duration: float
    virality_score: float
    keywords: List[str]

    # Detailed scoring breakdown
    speech_energy: float
    face_presence: float
    scene_changes: int
    keyword_count: int


class GeneratedClip(BaseModel):
    """Generated clip with Drive URL."""

    clip_number: int
    drive_url: str
    drive_file_id: str
    start_time: float
    end_time: float
    duration: float
    virality_score: Optional[float] = None  # None for manual mode
    keywords: Optional[List[str]] = None    # None for manual mode


class SmartClipsAnalyzePayload(BaseModel):
    """Webhook payload for analyze_only mode."""

    status: Literal["success"] = "success"
    mode: Literal["analyze_only"] = "analyze_only"
    analyzed_segments: List[AnalyzedSegment]
    total_segments: int
    source_duration: float
    recommendation: str  # Human-readable recommendation


class SmartClipsGeneratePayload(BaseModel):
    """Webhook payload for auto_generate and manual_generate modes."""

    status: Literal["success"] = "success"
    mode: Literal["auto_generate", "manual_generate"]
    clips: List[GeneratedClip]
    total_clips: int
    source_duration: float
