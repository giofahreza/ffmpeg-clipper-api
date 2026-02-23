"""Router for /api/v1/ffmpeg-compose endpoint (multi-task)."""

import logging
import uuid
from fastapi import APIRouter, BackgroundTasks

from app.models.common import AcceptedResponse, ErrorPayload
from app.models.ffmpeg_compose import (
    FFmpegComposeRequest,
    AddCaptionsRequest,
    StitchImagesRequest,
    FFmpegComposeSuccessPayload,
    ComposedMediaResult
)
from app.services.gdrive import (
    create_drive_client,
    validate_google_drive,
    download_from_google_drive,
    upload_to_google_drive
)
from app.services.finisher import burn_captions
from app.services.stitcher import create_slideshow
from app.utils.job_dir import job_directory
from app.utils.webhook import send_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


async def process_add_captions(job_id: str, request: AddCaptionsRequest):
    """Background task for caption burn-in."""
    with job_directory(job_id) as job_dir:
        try:
            # Validate Drive access
            credentials = request.google_drive.credentials.model_dump()
            validate_google_drive(
                credentials,
                request.google_drive.target_folder_id
            )

            # Download video and SRT
            drive = create_drive_client(credentials)
            video_path = f"{job_dir}/video.mp4"
            srt_path = f"{job_dir}/captions.srt"

            download_from_google_drive(
                drive,
                request.google_drive.video_file_id,
                video_path
            )
            download_from_google_drive(
                drive,
                request.google_drive.srt_file_id,
                srt_path
            )

            # Burn captions
            output_path = f"{job_dir}/output_with_captions.mp4"
            burn_captions(
                video_path,
                srt_path,
                output_path,
                font=request.caption_styling.font,
                font_size=request.caption_styling.font_size,
                primary_color=request.caption_styling.primary_color,
                alignment=request.caption_styling.alignment,
                margin_v=request.caption_styling.margin_v
            )

            # Upload result
            drive_url, drive_file_id = upload_to_google_drive(
                drive,
                output_path,
                request.google_drive.target_folder_id,
                mime_type="video/mp4"
            )

            # Send success webhook
            payload = FFmpegComposeSuccessPayload(
                composed_media=ComposedMediaResult(
                    drive_url=drive_url,
                    drive_file_id=drive_file_id
                )
            )
            await send_webhook(request.webhook_callback, payload.model_dump())

        except Exception as e:
            logger.error(f"Caption burn-in failed: {e}", exc_info=True)
            payload = ErrorPayload(error_message=str(e))
            await send_webhook(request.webhook_callback, payload.model_dump())


async def process_stitch_images(job_id: str, request: StitchImagesRequest):
    """Background task for image slideshow creation."""
    with job_directory(job_id) as job_dir:
        try:
            # Validate Drive access
            credentials = request.google_drive.credentials.model_dump()
            validate_google_drive(
                credentials,
                request.google_drive.target_folder_id
            )

            # Download images and audio
            drive = create_drive_client(credentials)
            image_paths = []

            for i, image_id in enumerate(request.google_drive.image_ids):
                image_path = f"{job_dir}/image_{i}.jpg"
                download_from_google_drive(drive, image_id, image_path)
                image_paths.append(image_path)

            audio_path = f"{job_dir}/audio.mp3"
            download_from_google_drive(
                drive,
                request.google_drive.audio_id,
                audio_path
            )

            # Create slideshow
            output_path = f"{job_dir}/slideshow.mp4"
            create_slideshow(
                image_paths,
                audio_path,
                output_path,
                duration_per_image=request.operations.duration_per_image,
                apply_ken_burns=request.operations.apply_ken_burns,
                resolution=request.operations.resolution
            )

            # Upload result
            drive_url, drive_file_id = upload_to_google_drive(
                drive,
                output_path,
                request.google_drive.target_folder_id,
                mime_type="video/mp4"
            )

            # Send success webhook
            payload = FFmpegComposeSuccessPayload(
                composed_media=ComposedMediaResult(
                    drive_url=drive_url,
                    drive_file_id=drive_file_id
                )
            )
            await send_webhook(request.webhook_callback, payload.model_dump())

        except Exception as e:
            logger.error(f"Image slideshow failed: {e}", exc_info=True)
            payload = ErrorPayload(error_message=str(e))
            await send_webhook(request.webhook_callback, payload.model_dump())


@router.post("/ffmpeg-compose", response_model=AcceptedResponse)
async def ffmpeg_compose_endpoint(
    request: FFmpegComposeRequest,
    background_tasks: BackgroundTasks
):
    """
    Multi-task FFmpeg composition endpoint.

    Handles:
    - task: "add_captions" - Burn SRT subtitles onto video
    - task: "stitch_images" - Create slideshow from images

    Returns 202 Accepted immediately and processes in background.
    """
    job_id = str(uuid.uuid4())

    if isinstance(request, AddCaptionsRequest):
        background_tasks.add_task(process_add_captions, job_id, request)
    elif isinstance(request, StitchImagesRequest):
        background_tasks.add_task(process_stitch_images, job_id, request)

    return AcceptedResponse(job_id=job_id)
