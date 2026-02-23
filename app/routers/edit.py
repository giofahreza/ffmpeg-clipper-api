"""Router for /api/v1/audio/edit endpoint."""

import logging
import uuid
from fastapi import APIRouter, BackgroundTasks

from app.models.common import AcceptedResponse, ErrorPayload
from app.models.edit import (
    EditRequest,
    EditSuccessPayload
)
from app.services.gdrive import (
    create_drive_client,
    validate_google_drive,
    download_from_google_drive,
    upload_to_google_drive
)
from app.services.audio_edit import (
    load_audio,
    process_operations,
    export_audio,
    get_duration_seconds
)
from app.utils.job_dir import job_directory
from app.utils.webhook import send_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


async def process_audio_edit(job_id: str, request: EditRequest):
    """Background task for audio editing."""
    with job_directory(job_id) as job_dir:
        try:
            # Validate Drive access
            credentials = request.google_drive.credentials.model_dump()
            validate_google_drive(
                credentials,
                request.google_drive.target_folder_id
            )

            # Download source audio
            drive = create_drive_client(credentials)
            source_file = f"{job_dir}/source.mp3"
            download_from_google_drive(
                drive,
                request.google_drive.source_file_id,
                source_file
            )

            # Load audio
            audio = load_audio(source_file)

            # Process operations sequentially
            operations = [op.model_dump() for op in request.operations]
            edited_audio = process_operations(
                audio,
                operations,
                job_dir,
                drive_client=drive
            )

            # Export result
            output_path = f"{job_dir}/edited.{request.output_format}"
            export_audio(edited_audio, output_path, format=request.output_format)

            # Get duration
            duration = get_duration_seconds(edited_audio)

            # Upload to Drive
            mime_types = {
                "mp3": "audio/mpeg",
                "wav": "audio/wav",
                "flac": "audio/flac"
            }
            mime_type = mime_types.get(request.output_format, "audio/mpeg")

            edited_url, edited_file_id = upload_to_google_drive(
                drive,
                output_path,
                request.google_drive.target_folder_id,
                mime_type=mime_type
            )

            # Send success webhook
            payload = EditSuccessPayload(
                edited_file_id=edited_file_id,
                edited_url=edited_url,
                duration_seconds=duration
            )
            await send_webhook(request.webhook_callback, payload.model_dump())

        except Exception as e:
            logger.error(f"Audio editing failed: {e}", exc_info=True)
            payload = ErrorPayload(error_message=str(e))
            await send_webhook(request.webhook_callback, payload.model_dump())


@router.post("/edit", response_model=AcceptedResponse)
async def edit_endpoint(
    request: EditRequest,
    background_tasks: BackgroundTasks
):
    """
    Edit audio with trim, merge, and volume operations.

    Operations are applied sequentially in array order.

    Returns 202 Accepted immediately and processes in background.
    """
    job_id = str(uuid.uuid4())
    background_tasks.add_task(process_audio_edit, job_id, request)

    return AcceptedResponse(job_id=job_id)
