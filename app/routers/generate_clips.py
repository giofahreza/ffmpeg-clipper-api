"""Router for /api/v1/generate-clips endpoint."""

import logging
import uuid
from fastapi import APIRouter, BackgroundTasks

from app.models.common import AcceptedResponse, ErrorPayload
from app.models.generate_clips import (
    GenerateClipsRequest,
    GenerateClipsSuccessPayload,
    ClipResult
)
from app.services.gdrive import (
    create_drive_client,
    validate_google_drive,
    download_from_google_drive,
    upload_to_google_drive
)
from app.services.cutter import generate_clips
from app.utils.job_dir import job_directory
from app.utils.webhook import send_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


async def process_clip_generation(job_id: str, request: GenerateClipsRequest):
    """Background task for clip generation."""
    with job_directory(job_id) as job_dir:
        try:
            # Validate Drive access
            credentials = request.google_drive.credentials.model_dump()
            validate_google_drive(
                credentials,
                request.google_drive.target_folder_id
            )

            # Download source video
            drive = create_drive_client(credentials)
            source_video = f"{job_dir}/source.mp4"
            download_from_google_drive(
                drive,
                request.google_drive.source_file_id,
                source_video
            )

            # Generate clips
            timestamps = [(ts.start, ts.end) for ts in request.timestamps]
            clip_paths = generate_clips(
                source_video,
                timestamps,
                job_dir,
                aspect_ratio=request.processing_rules.aspect_ratio,
                apply_face_tracking=request.processing_rules.apply_face_tracking
            )

            # Upload clips to Drive
            clips = []
            for clip_path in clip_paths:
                drive_url, drive_file_id = upload_to_google_drive(
                    drive,
                    clip_path,
                    request.google_drive.target_folder_id,
                    mime_type="video/mp4"
                )
                clips.append(ClipResult(
                    drive_url=drive_url,
                    drive_file_id=drive_file_id
                ))

            # Send success webhook
            payload = GenerateClipsSuccessPayload(clips=clips)
            await send_webhook(request.webhook_callback, payload.model_dump())

        except Exception as e:
            logger.error(f"Clip generation failed: {e}", exc_info=True)
            payload = ErrorPayload(error_message=str(e))
            await send_webhook(request.webhook_callback, payload.model_dump())


@router.post("/generate-clips", response_model=AcceptedResponse)
async def generate_clips_endpoint(
    request: GenerateClipsRequest,
    background_tasks: BackgroundTasks
):
    """
    Generate vertical clips from horizontal video with face tracking.

    Returns 202 Accepted immediately and processes in background.
    """
    job_id = str(uuid.uuid4())
    background_tasks.add_task(process_clip_generation, job_id, request)

    return AcceptedResponse(job_id=job_id)
