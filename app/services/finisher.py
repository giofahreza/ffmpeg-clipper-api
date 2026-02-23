"""Caption burn-in engine using FFmpeg ASS subtitles."""

import logging
import subprocess
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def srt_to_ass(srt_path: str, ass_path: str) -> None:
    """
    Convert SRT subtitle file to ASS format using FFmpeg.

    Args:
        srt_path: Input SRT file path
        ass_path: Output ASS file path
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", srt_path,
        ass_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Converted SRT to ASS: {ass_path}")


def apply_caption_styling(
    ass_path: str,
    font: str,
    font_size: int,
    primary_color: str,
    alignment: int,
    margin_v: int
) -> None:
    """
    Apply custom styling to ASS subtitle file.

    Args:
        ass_path: Path to ASS file (modified in-place)
        font: Font name
        font_size: Font size in points
        primary_color: ASS color format (&HAABBGGRR&)
        alignment: Alignment code (1-9, 2=bottom center)
        margin_v: Vertical margin in pixels
    """
    with open(ass_path, "r") as f:
        content = f.read()

    # Replace the Style: Default line
    style_pattern = r"Style: Default,.*"
    custom_style = (
        f"Style: Default,{font},{font_size},{primary_color},&H000000FF,"
        f"&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,"
        f"{alignment},10,10,{margin_v},1"
    )

    content = re.sub(style_pattern, custom_style, content)

    with open(ass_path, "w") as f:
        f.write(content)

    logger.info("Applied custom caption styling")


def burn_captions(
    video_path: str,
    srt_path: str,
    output_path: str,
    font: str = "Montserrat-Black",
    font_size: int = 24,
    primary_color: str = "&H00FFFF&",
    alignment: int = 2,
    margin_v: int = 150
) -> None:
    """
    Burn captions onto video using ASS subtitles.

    Args:
        video_path: Source video file
        srt_path: SRT subtitle file
        output_path: Output video file
        font: Font name
        font_size: Font size in points
        primary_color: ASS color format
        alignment: Alignment code
        margin_v: Vertical margin
    """
    # Convert SRT to ASS
    ass_path = Path(srt_path).with_suffix(".ass")
    srt_to_ass(srt_path, str(ass_path))

    # Apply styling
    apply_caption_styling(
        str(ass_path),
        font,
        font_size,
        primary_color,
        alignment,
        margin_v
    )

    # Burn captions using FFmpeg
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Burned captions onto video: {output_path}")
