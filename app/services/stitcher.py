"""Image slideshow engine with Ken Burns effect and crossfade transitions."""

import logging
import subprocess
import random
from typing import List
from pathlib import Path

logger = logging.getLogger(__name__)


def create_ken_burns_clip(
    image_path: str,
    output_path: str,
    duration: float,
    resolution: str = "1080x1920"
) -> None:
    """
    Create a Ken Burns (zoom/pan) clip from a still image.

    Args:
        image_path: Input image file
        output_path: Output video clip
        duration: Duration in seconds
        resolution: Output resolution (widthxheight)
    """
    width, height = map(int, resolution.split("x"))

    # Random pan direction for variety
    zoom_start = 1.0
    zoom_end = 1.5
    pan_x = random.choice(["left", "center", "right"])
    pan_y = random.choice(["top", "center", "bottom"])

    # Pan coordinates
    pan_map = {
        "left": 0, "center": 0.5, "right": 1,
        "top": 0, "bottom": 1
    }

    x_pan = pan_map.get(pan_x, 0.5)
    y_pan = pan_map.get(pan_y, 0.5)

    # FFmpeg zoompan filter
    fps = 30
    total_frames = int(duration * fps)

    zoompan_filter = (
        f"zoompan=z='min(zoom+0.0015,{zoom_end})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={width}x{height}:fps={fps}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", zoompan_filter,
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Created Ken Burns clip: {output_path}")


def create_static_clip(
    image_path: str,
    output_path: str,
    duration: float,
    resolution: str = "1080x1920"
) -> None:
    """
    Create a static video clip from an image (no Ken Burns).

    Args:
        image_path: Input image file
        output_path: Output video clip
        duration: Duration in seconds
        resolution: Output resolution
    """
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", f"scale={resolution}:force_original_aspect_ratio=decrease,pad={resolution}:(ow-iw)/2:(oh-ih)/2",
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Created static clip: {output_path}")


def stitch_with_crossfade(
    clip_paths: List[str],
    audio_path: str,
    output_path: str,
    transition_duration: float = 0.5
) -> None:
    """
    Stitch video clips with crossfade transitions and audio.

    Args:
        clip_paths: List of video clip paths
        audio_path: Audio file path
        output_path: Output video file
        transition_duration: Crossfade duration in seconds
    """
    if len(clip_paths) == 1:
        # Single clip, just mux with audio
        cmd = [
            "ffmpeg", "-y",
            "-i", clip_paths[0],
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path
        ]
    else:
        # Multiple clips with crossfade
        # Build complex filter for xfade transitions
        filter_parts = []
        inputs = []

        for i, clip in enumerate(clip_paths):
            inputs.extend(["-i", clip])

        inputs.extend(["-i", audio_path])

        # Build xfade chain
        current_output = "[0:v]"

        for i in range(1, len(clip_paths)):
            prev_output = current_output
            current_output = f"[v{i}]"

            filter_parts.append(
                f"{prev_output}[{i}:v]xfade=transition=fade:duration={transition_duration}:offset=0{current_output}"
            )

        # Final output without label
        filter_chain = ";".join(filter_parts[:-1]) + ";" + filter_parts[-1].replace(current_output, "")

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_chain,
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path
        ]

    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Stitched clips with audio: {output_path}")


def create_slideshow(
    image_paths: List[str],
    audio_path: str,
    output_path: str,
    duration_per_image: float = 4.5,
    apply_ken_burns: bool = True,
    resolution: str = "1080x1920"
) -> None:
    """
    Create image slideshow with optional Ken Burns effect.

    Args:
        image_paths: List of image file paths
        audio_path: Audio file path
        output_path: Output video file
        duration_per_image: Seconds per image
        apply_ken_burns: Apply zoom/pan effect
        resolution: Output resolution
    """
    job_dir = Path(output_path).parent
    clip_paths = []

    # Create individual clips from images
    for i, image_path in enumerate(image_paths):
        clip_path = job_dir / f"image_clip_{i}.mp4"

        if apply_ken_burns:
            create_ken_burns_clip(
                image_path,
                str(clip_path),
                duration_per_image,
                resolution
            )
        else:
            create_static_clip(
                image_path,
                str(clip_path),
                duration_per_image,
                resolution
            )

        clip_paths.append(str(clip_path))

    # Stitch clips with crossfade and audio
    stitch_with_crossfade(clip_paths, audio_path, output_path)
